import io

import qrcode
from django.contrib import messages
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from accounts.models import User
from core.mixins import CustomerRequiredMixin
from notifications.models import Notification
from organizations.models import Organization
from queue_management.models import Queue, Token
from services.models import Service


def _active_token_count(customer, organization):
    return Token.objects.filter(
        queue__service__organization=organization,
        customer=customer,
        status__in=Token.ACTIVE_STATUSES,
    ).count()


class HomeView(CustomerRequiredMixin, TemplateView):
    template_name = 'customers/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        hour = timezone.localtime().hour
        if hour < 12:
            greeting = 'Good Morning'
        elif hour < 17:
            greeting = 'Good Afternoon'
        else:
            greeting = 'Good Evening'
        context['greeting'] = greeting

        active_tokens = (
            Token.objects.filter(customer=user, status__in=Token.ACTIVE_STATUSES)
            .select_related('queue__service__organization', 'queue__service__department')
            .order_by('token_number')
        )
        context['active_tokens'] = active_tokens
        primary_token = active_tokens.first()
        context['primary_token'] = primary_token
        if primary_token:
            total_issued = primary_token.queue.last_token_number or 1
            completed_today = primary_token.queue.completed_tokens_today.count()
            context['queue_progress_pct'] = min(round((completed_today / total_issued) * 100), 100)
        else:
            context['queue_progress_pct'] = 0

        context['unread_notification_count'] = Notification.objects.filter(
            user=user, is_read=False,
        ).count()
        context['recent_notifications'] = Notification.objects.filter(user=user).order_by('-created_at')[:4]

        all_tokens = Token.objects.filter(customer=user).select_related('queue__service__organization')
        context['stats'] = {
            'active_count': active_tokens.count(),
            'completed_count': all_tokens.filter(status=Token.Status.COMPLETED).count(),
            'cancelled_count': all_tokens.filter(status=Token.Status.CANCELLED).count(),
        }
        context['recent_activity'] = all_tokens.select_related(
            'queue__service__organization',
        ).order_by('-created_at')[:6]

        today = timezone.localdate()
        candidate_orgs = list(Organization.objects.filter(is_approved=True, is_active=True))
        org_ids = [org.id for org in candidate_orgs]
        waiting_counts = dict(
            Token.objects.filter(
                queue__service__organization_id__in=org_ids,
                queue__queue_date=today,
                status=Token.Status.WAITING,
            ).values_list('queue__service__organization_id').annotate(count=Count('id'))
            .values_list('queue__service__organization_id', 'count'),
        )
        for org in candidate_orgs:
            org.waiting_count = waiting_counts.get(org.id, 0)
            org.is_open = org.is_open_now()
        open_orgs = sorted((o for o in candidate_orgs if o.is_open), key=lambda o: o.waiting_count)
        closed_orgs = [o for o in candidate_orgs if not o.is_open]
        context['recommended_organizations'] = (open_orgs + closed_orgs)[:3]

        return context


class ScanQRView(CustomerRequiredMixin, TemplateView):
    template_name = 'customers/scan.html'


class ScanLookupView(CustomerRequiredMixin, View):
    def get(self, request):
        code = request.GET.get('code', '').strip()
        slug = code.rstrip('/').split('/')[-1] if code else ''
        organization = Organization.objects.filter(slug=slug, is_approved=True, is_active=True).first()
        if organization:
            return redirect('customers:select_service', slug=organization.slug)
        messages.error(request, "We couldn't find an organization for that code. Please try again.")
        return redirect('customers:scan')


class SelectOrganizationView(ListView):
    model = Organization
    template_name = 'customers/select_organization.html'
    context_object_name = 'organizations'
    paginate_by = 20

    def get_queryset(self):
        queryset = Organization.objects.filter(is_approved=True, is_active=True)
        query = self.request.GET.get('q', '').strip()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(city__icontains=query))
        category = self.request.GET.get('category', '').strip()
        if category:
            queryset = queryset.filter(category=category)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        context['selected_category'] = self.request.GET.get('category', '')
        context['category_choices'] = Organization.Category.choices

        today = timezone.localdate()
        all_approved = list(Organization.objects.filter(is_approved=True, is_active=True))
        all_ids = [org.id for org in all_approved]

        waiting_counts = dict(
            Token.objects.filter(
                queue__service__organization_id__in=all_ids,
                queue__queue_date=today,
                status=Token.Status.WAITING,
            )
            .values_list('queue__service__organization_id')
            .annotate(count=Count('id'))
            .values_list('queue__service__organization_id', 'count'),
        )
        avg_minutes_by_org = dict(
            Service.objects.filter(organization_id__in=all_ids, is_active=True)
            .values_list('organization_id')
            .annotate(avg=Avg('average_service_minutes'))
            .values_list('organization_id', 'avg'),
        )

        page_orgs = context['organizations']
        open_now_count = 0
        for org in all_approved:
            if org.is_open_now():
                open_now_count += 1

        for org in page_orgs:
            org.waiting_count = waiting_counts.get(org.id, 0)
            avg_minutes = avg_minutes_by_org.get(org.id) or 10
            org.estimated_wait = round(org.waiting_count * avg_minutes)
            org.is_open = org.is_open_now()

        category_queue_status = []
        for value, label in Organization.Category.choices:
            org_ids_in_category = [o.id for o in all_approved if o.category == value]
            total_waiting = sum(waiting_counts.get(oid, 0) for oid in org_ids_in_category)
            if org_ids_in_category:
                category_queue_status.append({'label': label, 'count': total_waiting})

        popular_organizations = sorted(
            all_approved, key=lambda o: waiting_counts.get(o.id, 0), reverse=True,
        )[:5]
        for org in popular_organizations:
            org.waiting_count = waiting_counts.get(org.id, 0)

        context['stats'] = {
            'organization_count': len(all_ids),
            'customer_count': User.objects.filter(role=User.Role.CUSTOMER).count(),
            'token_count': Token.objects.count(),
            'open_now_count': open_now_count,
        }
        context['category_queue_status'] = category_queue_status
        context['popular_organizations'] = popular_organizations
        return context


class SelectServiceView(DetailView):
    model = Organization
    template_name = 'customers/select_service.html'
    context_object_name = 'organization'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        return Organization.objects.filter(is_approved=True, is_active=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        services = self.object.services.filter(is_active=True).select_related('department')
        today = timezone.localdate()
        todays_queues = {
            queue.service_id: queue
            for queue in Queue.objects.filter(service__in=services, queue_date=today)
        }
        for service in services:
            queue = todays_queues.get(service.id)
            serving = queue.currently_serving if queue else None
            service.is_queue_open = bool(queue and queue.status == Queue.Status.OPEN)
            service.currently_serving_number = serving.display_number if serving else None
            service.waiting_count = queue.waiting_tokens.count() if queue else 0
        context['services'] = services
        context['total_waiting'] = sum(s.waiting_count for s in services)
        context['open_services_count'] = sum(1 for s in services if s.is_queue_open)
        context['is_open'] = self.object.is_open_now()
        return context


class BookTokenView(CustomerRequiredMixin, View):
    def post(self, request, service_id):
        service = get_object_or_404(Service, pk=service_id, is_active=True)
        organization = service.organization
        queue = Queue.get_or_create_today(service)

        existing_token = Token.objects.filter(
            queue=queue, customer=request.user, status__in=Token.ACTIVE_STATUSES,
        ).first()
        if existing_token:
            messages.info(request, 'You already have an active token for this service today.')
            return redirect('customers:token_detail', pk=existing_token.pk)

        if _active_token_count(request.user, organization) >= organization.max_active_tokens_per_customer:
            messages.error(
                request,
                f'You can have at most {organization.max_active_tokens_per_customer} '
                f'active token(s) at {organization.name} at a time.',
            )
            return redirect('customers:select_service', slug=organization.slug)

        token = queue.issue_token(customer=request.user)
        messages.success(request, f'Token {token.display_number} booked!')
        return redirect('customers:token_detail', pk=token.pk)


class TokenDetailView(CustomerRequiredMixin, DetailView):
    model = Token
    template_name = 'customers/token_detail.html'
    context_object_name = 'token'

    def get_queryset(self):
        return Token.objects.filter(customer=self.request.user).select_related(
            'queue__service__organization',
        )


def _build_token_qr_png(request, token):
    target_url = request.build_absolute_uri(
        reverse('customers:token_detail', kwargs={'pk': token.pk}),
    )
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=3)
    qr.add_data(target_url)
    qr.make(fit=True)
    image = qr.make_image(fill_color='#2563EB', back_color='#FFFFFF').convert('RGB')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer


class TokenQRView(CustomerRequiredMixin, View):
    def get(self, request, pk):
        token = get_object_or_404(Token, pk=pk, customer=request.user)
        return HttpResponse(_build_token_qr_png(request, token), content_type='image/png')


class TokenPDFView(CustomerRequiredMixin, View):
    def get(self, request, pk):
        from reportlab.lib.pagesizes import A6
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

        token = get_object_or_404(
            Token.objects.select_related('queue__service__organization', 'queue__service__department'),
            pk=pk, customer=request.user,
        )
        organization = token.queue.service.organization
        styles = getSampleStyleSheet()

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A6, title=f'Token {token.display_number}', topMargin=20, bottomMargin=20)
        elements = [
            Paragraph('QueueLess Nepal', styles['Heading3']),
            Paragraph(organization.name, styles['Normal']),
            Spacer(1, 10),
            Paragraph(token.display_number, styles['Title']),
            Spacer(1, 6),
            Paragraph(token.queue.service.name, styles['Normal']),
        ]
        if token.queue.service.department:
            elements.append(Paragraph(token.queue.service.department.name, styles['Normal']))
        elements += [
            Spacer(1, 10),
            Image(_build_token_qr_png(request, token), width=110, height=110),
            Spacer(1, 10),
            Paragraph(f'Status: {token.get_status_display()}', styles['Normal']),
            Paragraph(f'Booked: {timezone.localtime(token.created_at).strftime("%b %d, %Y %I:%M %p")}', styles['Normal']),
            Paragraph(f'Reference: {str(token.pk)[:8].upper()}', styles['Normal']),
        ]
        doc.build(elements)
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{token.display_number}-token.pdf"'
        return response


class TokenStatusJSONView(CustomerRequiredMixin, View):
    def get(self, request, pk):
        token = get_object_or_404(Token, pk=pk, customer=request.user)
        serving = token.queue.currently_serving
        return JsonResponse({
            'status': token.status,
            'status_display': token.get_status_display(),
            'position_in_queue': token.position_in_queue,
            'estimated_wait_minutes': token.estimated_wait_minutes,
            'currently_serving': serving.display_number if serving else None,
            'display_number': token.display_number,
        })


class CancelTokenView(CustomerRequiredMixin, View):
    def post(self, request, pk):
        token = get_object_or_404(Token, pk=pk, customer=request.user)
        if token.status in Token.ACTIVE_STATUSES:
            token.cancel()
            messages.success(request, f'Token {token.display_number} has been cancelled.')
        else:
            messages.error(request, 'This token can no longer be cancelled.')
        return redirect('customers:token_history')


class RebookTokenView(CustomerRequiredMixin, View):
    def post(self, request, pk):
        old_token = get_object_or_404(Token, pk=pk, customer=request.user)
        service = old_token.queue.service
        organization = service.organization

        if not organization.allow_customer_rebooking:
            messages.error(request, f'{organization.name} does not allow rebooking from a past token.')
            return redirect('customers:token_history')

        if not service.is_active:
            messages.error(request, 'This service is no longer available.')
            return redirect('customers:token_history')

        queue = Queue.get_or_create_today(service)
        existing_token = Token.objects.filter(
            queue=queue, customer=request.user, status__in=Token.ACTIVE_STATUSES,
        ).first()
        if existing_token:
            messages.info(request, 'You already have an active token for this service today.')
            return redirect('customers:token_detail', pk=existing_token.pk)

        if _active_token_count(request.user, organization) >= organization.max_active_tokens_per_customer:
            messages.error(
                request,
                f'You can have at most {organization.max_active_tokens_per_customer} '
                f'active token(s) at {organization.name} at a time.',
            )
            return redirect('customers:token_history')

        new_token = queue.issue_token(customer=request.user)
        messages.success(request, f'Rebooked! Your new token is {new_token.display_number}.')
        return redirect('customers:token_detail', pk=new_token.pk)


class TokenHistoryView(CustomerRequiredMixin, ListView):
    model = Token
    template_name = 'customers/token_history.html'
    context_object_name = 'tokens'
    paginate_by = 12

    def _base_queryset(self):
        """All filters except status — used both for the list and for the
        per-tab counts, so counts reflect the current search/office/date filters."""
        queryset = Token.objects.filter(customer=self.request.user).select_related(
            'queue__service__organization', 'queue__service__department',
        )

        query = self.request.GET.get('q', '').strip()
        if query:
            text_match = (
                Q(queue__service__organization__name__icontains=query)
                | Q(queue__service__name__icontains=query)
                | Q(queue__service__department__name__icontains=query)
            )
            if query.isdigit():
                text_match |= Q(token_number=int(query))
            queryset = queryset.filter(text_match)

        office_id = self.request.GET.get('office', '').strip()
        if office_id:
            queryset = queryset.filter(queue__service__organization_id=office_id)

        date_from = self.request.GET.get('date_from', '').strip()
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)

        date_to = self.request.GET.get('date_to', '').strip()
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        return queryset

    def get_queryset(self):
        queryset = self._base_queryset()

        status = self.request.GET.get('status', '').strip()
        if status:
            queryset = queryset.filter(status=status)

        sort = self.request.GET.get('sort', 'newest')
        if sort == 'oldest':
            queryset = queryset.order_by('created_at')
        elif sort == 'updated':
            queryset = queryset.order_by('-updated_at')
        else:
            queryset = queryset.order_by('-created_at')
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        for token in context['tokens']:
            token.is_active_token = token.status in Token.ACTIVE_STATUSES

        context['status_choices'] = Token.Status.choices
        context['selected_status'] = self.request.GET.get('status', '')
        context['search_query'] = self.request.GET.get('q', '')
        context['selected_office'] = self.request.GET.get('office', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        context['selected_sort'] = self.request.GET.get('sort', 'newest')

        filtered_base = self._base_queryset()
        context['status_counts'] = dict(
            filtered_base.values_list('status').annotate(count=Count('id')).values_list('status', 'count'),
        )
        context['total_filtered_count'] = filtered_base.count()

        context['booking_offices'] = Organization.objects.filter(
            services__queues__tokens__customer=user,
        ).distinct().order_by('name')

        all_tokens = Token.objects.filter(customer=user)
        wait_stats = all_tokens.filter(called_at__isnull=False).annotate(
            wait_duration=ExpressionWrapper(F('called_at') - F('created_at'), output_field=DurationField()),
        ).aggregate(avg_wait=Avg('wait_duration'))
        avg_wait_minutes = round(wait_stats['avg_wait'].total_seconds() / 60) if wait_stats['avg_wait'] else 0

        context['stats'] = {
            'total': all_tokens.count(),
            'active': all_tokens.filter(status__in=Token.ACTIVE_STATUSES).count(),
            'completed': all_tokens.filter(status=Token.Status.COMPLETED).count(),
            'cancelled': all_tokens.filter(status=Token.Status.CANCELLED).count(),
            'avg_wait_minutes': avg_wait_minutes,
        }
        return context


class NotificationListView(CustomerRequiredMixin, ListView):
    model = Notification
    template_name = 'customers/notifications.html'
    context_object_name = 'notifications'
    paginate_by = 30

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return response
