import io
import os
import subprocess
from datetime import date, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.forms import SetPasswordForm
from django.db.models import Count, F, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, TemplateView, UpdateView

from accounts.models import User
from core.models import ActivityLog, PlatformSettings, log_activity
from notifications.models import Notification
from organizations.forms import OrganizationProfileForm
from organizations.models import Organization
from payments.models import Payment
from queue_management.models import Queue, Token
from services.models import Service
from staff.models import StaffProfile
from subscriptions.models import Subscription, SubscriptionPlan

from .forms import (
    AnnouncementForm,
    OrganizationCreateForm,
    PaymentForm,
    PlanEditForm,
    PlatformSettingsForm,
    SubscriptionAssignForm,
)
from .mixins import SuperAdminRequiredMixin


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class PlatformDashboardView(SuperAdminRequiredMixin, TemplateView):
    template_name = 'dashboard/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        month_start = today.replace(day=1)

        trend_labels, trend_counts = [], []
        for offset in range(6, -1, -1):
            day = today - timedelta(days=offset)
            trend_labels.append(day.strftime('%a'))
            trend_counts.append(Token.objects.filter(queue__queue_date=day).count())

        active_subscriptions = Subscription.objects.filter(
            status=Subscription.Status.ACTIVE,
        ).select_related('organization', 'plan')
        expiring_soon = [sub for sub in active_subscriptions if sub.is_expiring_soon]

        context.update({
            'stats': {
                'total_organizations': Organization.objects.count(),
                'pending_approvals': Organization.objects.filter(is_approved=False).count(),
                'total_customers': User.objects.filter(role=User.Role.CUSTOMER).count(),
                'total_staff': StaffProfile.objects.filter(is_active=True).count(),
                'active_queues': Queue.objects.filter(queue_date=today, status=Queue.Status.OPEN).count(),
                'revenue_this_month': Payment.objects.filter(
                    status=Payment.Status.SUCCESS, paid_at__date__gte=month_start,
                ).aggregate(total=Sum('amount'))['total'] or 0,
            },
            'trend_labels': trend_labels,
            'trend_counts': trend_counts,
            'expiring_soon': expiring_soon[:5],
            'recent_activity': ActivityLog.objects.select_related('actor')[:8],
        })
        return context


# ---------------------------------------------------------------------------
# Organization management
# ---------------------------------------------------------------------------

class OrganizationListView(SuperAdminRequiredMixin, ListView):
    template_name = 'dashboard/organization_list.html'
    context_object_name = 'organizations'
    paginate_by = 20

    def get_queryset(self):
        queryset = Organization.objects.select_related('owner').order_by('-created_at')
        status = self.request.GET.get('status', '')
        if status == 'pending':
            queryset = queryset.filter(is_approved=False)
        elif status == 'suspended':
            queryset = queryset.filter(is_active=False)
        elif status == 'active':
            queryset = queryset.filter(is_approved=True, is_active=True)
        query = self.request.GET.get('q', '').strip()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(city__icontains=query))
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['selected_status'] = self.request.GET.get('status', '')
        context['query'] = self.request.GET.get('q', '')
        context['pending_count'] = Organization.objects.filter(is_approved=False).count()
        return context


class OrganizationCreateView(SuperAdminRequiredMixin, View):
    template_name = 'dashboard/organization_create.html'

    def get(self, request):
        return render(request, self.template_name, {'form': OrganizationCreateForm()})

    def post(self, request):
        form = OrganizationCreateForm(request.POST)
        if form.is_valid():
            owner = form.save()
            log_activity(
                ActivityLog.Action.ORG_CREATED,
                f'{owner.organizations.first().name} created by {request.user}',
                actor=request.user, request=request,
            )
            messages.success(
                request,
                f'{owner.organizations.first().name} created — pending a subscription plan and '
                f'payment before it goes live.',
            )
            return redirect('dashboard:organizations')
        return render(request, self.template_name, {'form': form})


class OrganizationUpdateView(SuperAdminRequiredMixin, UpdateView):
    model = Organization
    form_class = OrganizationProfileForm
    template_name = 'dashboard/organization_edit.html'
    success_url = reverse_lazy('dashboard:organizations')

    def form_valid(self, form):
        messages.success(self.request, 'Organization updated.')
        return super().form_valid(form)


class OrganizationApproveView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        org = get_object_or_404(Organization, pk=pk)
        org.is_approved = True
        org.save(update_fields=['is_approved'])
        Notification.objects.create(
            user=org.owner,
            notification_type=Notification.NotificationType.GENERAL,
            title='Organization approved',
            message=f'{org.name} has been approved and is now live on QueueLess Nepal.',
        )
        log_activity(ActivityLog.Action.ORG_APPROVED, org.name, actor=request.user, request=request)
        messages.success(request, f'{org.name} approved.')
        return redirect('dashboard:organizations')


class OrganizationSuspendView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        org = get_object_or_404(Organization, pk=pk)
        org.is_active = not org.is_active
        org.save(update_fields=['is_active'])
        action = ActivityLog.Action.ORG_SUSPENDED if not org.is_active else ActivityLog.Action.ORG_REACTIVATED
        log_activity(action, org.name, actor=request.user, request=request)
        messages.success(request, f'{org.name} {"suspended" if not org.is_active else "reactivated"}.')
        return redirect('dashboard:organizations')


class OrganizationDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        org = get_object_or_404(Organization, pk=pk)
        if Token.objects.filter(queue__service__organization=org).exists():
            messages.error(request, f'Cannot delete {org.name} — it has queue/token history. Suspend it instead.')
        else:
            name = org.name
            org.delete()
            log_activity(ActivityLog.Action.ORG_DELETED, name, actor=request.user, request=request)
            messages.success(request, f'{name} deleted.')
        return redirect('dashboard:organizations')


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

def _user_export_queryset(request):
    """Shared filtered queryset for the user list, CSV export, and PDF export —
    kept in one place so all three always agree on what "the current filter" means."""
    queryset = User.objects.select_related('staff_profile__organization').prefetch_related(
        'organizations__subscription__plan',
    )

    role = request.GET.get('role', '')
    if role in dict(User.Role.choices):
        queryset = queryset.filter(role=role)

    status = request.GET.get('status', '')
    if status == 'active':
        queryset = queryset.filter(is_active=True)
    elif status == 'inactive':
        queryset = queryset.filter(is_active=False)

    verification = request.GET.get('verified', '')
    if verification == 'verified':
        queryset = queryset.filter(is_verified=True)
    elif verification == 'unverified':
        queryset = queryset.filter(is_verified=False)

    query = request.GET.get('q', '').strip()
    if query:
        queryset = queryset.filter(
            Q(username__icontains=query) | Q(email__icontains=query)
            | Q(first_name__icontains=query) | Q(last_name__icontains=query)
            | Q(phone_number__icontains=query)
            | Q(organizations__name__icontains=query) | Q(staff_profile__organization__name__icontains=query),
        ).distinct()

    sort = request.GET.get('sort', 'newest')
    if sort == 'oldest':
        queryset = queryset.order_by('date_joined')
    elif sort == 'alphabetical':
        queryset = queryset.order_by('first_name', 'username')
    elif sort == 'last_login':
        queryset = queryset.order_by(F('last_login').desc(nulls_last=True))
    else:
        queryset = queryset.order_by('-date_joined')
    return queryset


def _attach_primary_organization(users):
    for u in users:
        if u.role == User.Role.ORG_ADMIN:
            owned = list(u.organizations.all())
            u.primary_organization = owned[0] if owned else None
        elif u.role == User.Role.STAFF:
            u.primary_organization = getattr(u, 'staff_profile', None) and u.staff_profile.organization
        else:
            u.primary_organization = None
    return users


class UserListView(SuperAdminRequiredMixin, ListView):
    template_name = 'dashboard/user_list.html'
    context_object_name = 'users'

    def get_paginate_by(self, queryset):
        try:
            per_page = int(self.request.GET.get('per_page', 25))
        except ValueError:
            per_page = 25
        return per_page if per_page in (10, 25, 50, 100) else 25

    def get_queryset(self):
        return _user_export_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        _attach_primary_organization(context['users'])

        context['selected_role'] = self.request.GET.get('role', '')
        context['selected_status'] = self.request.GET.get('status', '')
        context['selected_verified'] = self.request.GET.get('verified', '')
        context['selected_sort'] = self.request.GET.get('sort', 'newest')
        context['per_page'] = self.get_paginate_by(None)
        context['per_page_options'] = [10, 25, 50, 100]
        context['query'] = self.request.GET.get('q', '')
        context['role_choices'] = User.Role.choices

        all_users = User.objects.all()
        month_start = timezone.localdate().replace(day=1)
        stats = {
            'total': all_users.count(),
            'customers': all_users.filter(role=User.Role.CUSTOMER).count(),
            'org_admins': all_users.filter(role=User.Role.ORG_ADMIN).count(),
            'staff': all_users.filter(role=User.Role.STAFF).count(),
            'super_admins': all_users.filter(role=User.Role.SUPER_ADMIN).count(),
            'active': all_users.filter(is_active=True).count(),
            'inactive': all_users.filter(is_active=False).count(),
            'new_this_month': all_users.filter(date_joined__date__gte=month_start).count(),
        }
        context['stats'] = stats
        context['role_breakdown'] = [
            ('Customers', stats['customers']),
            ('Organization Admins', stats['org_admins']),
            ('Staff', stats['staff']),
            ('Super Admins', stats['super_admins']),
        ]
        return context


class UserExportCSVView(SuperAdminRequiredMixin, View):
    def get(self, request):
        import csv

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="users.csv"'
        writer = csv.writer(response)
        writer.writerow(['Name', 'Username', 'Email', 'Phone', 'Role', 'Status', 'Verified', 'Joined', 'Last Login'])
        for u in _user_export_queryset(request):
            writer.writerow([
                u.get_full_name() or u.username, u.username, u.email, u.phone_number or '',
                u.get_role_display(), 'Active' if u.is_active else 'Inactive',
                'Yes' if u.is_verified else 'No',
                timezone.localtime(u.date_joined).strftime('%Y-%m-%d'),
                timezone.localtime(u.last_login).strftime('%Y-%m-%d %H:%M') if u.last_login else '',
            ])
        return response


class UserExportPDFView(SuperAdminRequiredMixin, View):
    def get(self, request):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
        from reportlab.lib.styles import getSampleStyleSheet

        styles = getSampleStyleSheet()
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), title='QueueLess Nepal — Users')
        rows = [['Name', 'Username', 'Email', 'Role', 'Status', 'Joined']]
        for u in _user_export_queryset(request):
            rows.append([
                u.get_full_name() or u.username, u.username, u.email, u.get_role_display(),
                'Active' if u.is_active else 'Inactive',
                timezone.localtime(u.date_joined).strftime('%Y-%m-%d'),
            ])
        table = Table(rows, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563EB')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
        ]))
        doc.build([Paragraph('QueueLess Nepal — Users', styles['Title']), table])
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="users.pdf"'
        return response


class UserDetailJSONView(SuperAdminRequiredMixin, View):
    def get(self, request, pk):
        target = get_object_or_404(User, pk=pk)

        organization = None
        department = None
        subscription = None
        if target.role == User.Role.ORG_ADMIN:
            org = target.organizations.first()
            if org:
                organization = org.name
                if getattr(org, 'subscription', None):
                    subscription = org.subscription.plan.get_tier_display()
        elif target.role == User.Role.STAFF:
            staff_profile = getattr(target, 'staff_profile', None)
            if staff_profile:
                organization = staff_profile.organization.name
                department = staff_profile.department.name if staff_profile.department else None

        activity = []
        if target.role == User.Role.CUSTOMER:
            for token in Token.objects.filter(customer=target).select_related(
                'queue__service__organization',
            ).order_by('-created_at')[:8]:
                activity.append({
                    'label': f'{token.get_status_display()} — {token.display_number}',
                    'meta': f'{token.queue.service.name} · {token.queue.service.organization.name}',
                    'when': timezone.localtime(token.created_at).strftime('%b %d, %Y %I:%M %p'),
                })
        else:
            for log in ActivityLog.objects.filter(actor=target).order_by('-created_at')[:8]:
                activity.append({
                    'label': log.get_action_display(),
                    'meta': log.description,
                    'when': timezone.localtime(log.created_at).strftime('%b %d, %Y %I:%M %p'),
                })

        login_history = [
            {
                'when': timezone.localtime(log.created_at).strftime('%b %d, %Y %I:%M %p'),
                'ip': log.ip_address or 'Unknown',
            }
            for log in ActivityLog.objects.filter(
                actor=target, action=ActivityLog.Action.LOGIN,
            ).order_by('-created_at')[:5]
        ]

        return JsonResponse({
            'full_name': target.get_full_name() or target.username,
            'username': target.username,
            'email': target.email,
            'phone': str(target.phone_number) if target.phone_number else None,
            'role': target.get_role_display(),
            'organization': organization,
            'department': department,
            'subscription': subscription,
            'is_active': target.is_active,
            'is_verified': target.is_verified,
            'date_joined': timezone.localtime(target.date_joined).strftime('%b %d, %Y'),
            'last_login': timezone.localtime(target.last_login).strftime('%b %d, %Y %I:%M %p') if target.last_login else None,
            'profile_picture_url': target.profile_picture.url if target.profile_picture else None,
            'activity': activity,
            'login_history': login_history,
        })


class UserBulkActionView(SuperAdminRequiredMixin, View):
    def post(self, request):
        action = request.POST.get('bulk_action', '')
        user_ids = request.POST.getlist('user_ids')
        targets = User.objects.filter(pk__in=user_ids).exclude(pk=request.user.pk)

        if action == 'activate':
            count = targets.update(is_active=True)
            for target in targets:
                log_activity(ActivityLog.Action.USER_UNBLOCKED, str(target), actor=request.user, request=request)
            messages.success(request, f'{count} user(s) activated.')
        elif action == 'suspend':
            count = targets.update(is_active=False)
            for target in targets:
                log_activity(ActivityLog.Action.USER_BLOCKED, str(target), actor=request.user, request=request)
            messages.success(request, f'{count} user(s) suspended.')
        else:
            messages.error(request, 'Unknown bulk action.')
        return redirect('dashboard:users')


class UserBlockView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        if target.pk == request.user.pk:
            messages.error(request, "You can't block your own account.")
            return redirect('dashboard:users')
        target.is_active = not target.is_active
        target.save(update_fields=['is_active'])
        action = ActivityLog.Action.USER_BLOCKED if not target.is_active else ActivityLog.Action.USER_UNBLOCKED
        log_activity(action, str(target), actor=request.user, request=request)
        messages.success(request, f'{target} {"blocked" if not target.is_active else "unblocked"}.')
        return redirect('dashboard:users')


class UserResetPasswordView(SuperAdminRequiredMixin, View):
    template_name = 'dashboard/user_reset_password.html'

    def get(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        form = SetPasswordForm(user=target)
        return render(request, self.template_name, {'form': form, 'target': target})

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        form = SetPasswordForm(user=target, data=request.POST)
        if form.is_valid():
            form.save()
            log_activity(ActivityLog.Action.PASSWORD_RESET, str(target), actor=request.user, request=request)
            messages.success(request, f"{target}'s password has been reset.")
            return redirect('dashboard:users')
        return render(request, self.template_name, {'form': form, 'target': target})


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

class SubscriptionListView(SuperAdminRequiredMixin, TemplateView):
    template_name = 'dashboard/subscription_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subscriptions = Subscription.objects.select_related('organization', 'plan').order_by('end_date')
        context.update({
            'plans': SubscriptionPlan.objects.all(),
            'subscriptions': subscriptions,
            'unsubscribed_orgs': Organization.objects.filter(subscription__isnull=True),
        })
        return context


class PlanUpdateView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        plan = get_object_or_404(SubscriptionPlan, pk=pk)
        form = PlanEditForm(request.POST, instance=plan)
        if form.is_valid():
            form.save()
            messages.success(request, f'{plan.get_tier_display()} plan updated.')
        else:
            messages.error(request, 'Could not update plan — please check the form.')
        return redirect('dashboard:subscriptions')


class SubscriptionAssignView(SuperAdminRequiredMixin, View):
    template_name = 'dashboard/subscription_assign.html'

    def get(self, request, org_pk):
        org = get_object_or_404(Organization, pk=org_pk, subscription__isnull=True)
        form = SubscriptionAssignForm()
        return render(request, self.template_name, {'form': form, 'organization': org})

    def post(self, request, org_pk):
        org = get_object_or_404(Organization, pk=org_pk, subscription__isnull=True)
        form = SubscriptionAssignForm(request.POST)
        if form.is_valid():
            Subscription.objects.create(
                organization=org,
                plan=form.cleaned_data['plan'],
                status=Subscription.Status.ACTIVE,
                end_date=timezone.localdate() + timedelta(days=30),
            )
            log_activity(
                ActivityLog.Action.SUBSCRIPTION_ASSIGNED, f'{org.name} → {form.cleaned_data["plan"]}',
                actor=request.user, request=request,
            )
            messages.success(request, f'{org.name} subscribed.')
            return redirect('dashboard:subscriptions')
        return render(request, self.template_name, {'form': form, 'organization': org})


class RenewSubscriptionView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        subscription = get_object_or_404(Subscription, pk=pk)
        subscription.renew(days=30)
        log_activity(
            ActivityLog.Action.SUBSCRIPTION_RENEWED, subscription.organization.name,
            actor=request.user, request=request,
        )
        messages.success(request, f'{subscription.organization.name} renewed until {subscription.end_date}.')
        return redirect('dashboard:subscriptions')


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

class PaymentListView(SuperAdminRequiredMixin, ListView):
    template_name = 'dashboard/payment_list.html'
    context_object_name = 'payments'
    paginate_by = 25

    def get_queryset(self):
        queryset = Payment.objects.select_related('subscription__organization').order_by('-paid_at')
        status = self.request.GET.get('status', '')
        if status in dict(Payment.Status.choices):
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['selected_status'] = self.request.GET.get('status', '')
        context['status_choices'] = Payment.Status.choices
        return context


class PaymentCreateView(SuperAdminRequiredMixin, View):
    template_name = 'dashboard/payment_form.html'

    def get(self, request):
        return render(request, self.template_name, self._context(PaymentForm()))

    def _context(self, form):
        return {
            'form': form,
            'unsubscribed_orgs': Organization.objects.filter(subscription__isnull=True),
        }

    def post(self, request):
        form = PaymentForm(request.POST)
        if form.is_valid():
            org = form.cleaned_data['organization']
            payment = Payment.objects.create(
                subscription=org.subscription,
                amount=form.cleaned_data['amount'],
                provider=form.cleaned_data['provider'],
                notes=form.cleaned_data.get('notes', ''),
                recorded_by=request.user,
            )
            log_activity(
                ActivityLog.Action.PAYMENT_RECORDED, f'{payment.amount} from {org.name}',
                actor=request.user, request=request,
            )
            messages.success(request, f'Payment {payment.transaction_id} recorded.')

            if not org.is_approved and payment.status == Payment.Status.SUCCESS:
                org.is_approved = True
                org.save(update_fields=['is_approved'])
                Notification.objects.create(
                    user=org.owner,
                    notification_type=Notification.NotificationType.GENERAL,
                    title='Organization approved',
                    message=f'{org.name} has been approved and is now live on QueueLess Nepal.',
                )
                log_activity(
                    ActivityLog.Action.ORG_APPROVED,
                    f'{org.name} auto-approved after plan + payment',
                    actor=request.user, request=request,
                )
                messages.info(request, f'{org.name} now has a plan and payment on file — it is live.')

            return redirect('dashboard:payments')
        return render(request, self.template_name, self._context(form))


class PaymentInvoicePDFView(SuperAdminRequiredMixin, View):
    def get(self, request, pk):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        payment = get_object_or_404(Payment.objects.select_related('subscription__organization'), pk=pk)
        styles = getSampleStyleSheet()

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, title=f'Invoice {payment.transaction_id}')
        elements = [
            Paragraph('QueueLess Nepal', styles['Title']),
            Paragraph(f'Invoice — {payment.transaction_id}', styles['Heading2']),
            Spacer(1, 16),
        ]
        table = Table([
            ['Organization', payment.subscription.organization.name],
            ['Plan', payment.subscription.plan.get_tier_display()],
            ['Amount', f'NPR {payment.amount}'],
            ['Provider', payment.get_provider_display()],
            ['Status', payment.get_status_display()],
            ['Paid at', payment.paid_at.strftime('%Y-%m-%d %H:%M')],
        ])
        table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F8FAFC')),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(table)
        doc.build(elements)
        buffer.seek(0)

        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="invoice-{payment.transaction_id}.pdf"'
        return response


class RevenueReportView(SuperAdminRequiredMixin, TemplateView):
    template_name = 'dashboard/revenue_report.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()

        monthly_labels, monthly_totals = [], []
        for offset in range(5, -1, -1):
            month_date = (today.replace(day=1) - timedelta(days=1)).replace(day=1) if offset else today
            # step back `offset` months from this month
            year = today.year
            month = today.month - offset
            while month <= 0:
                month += 12
                year -= 1
            total = Payment.objects.filter(
                status=Payment.Status.SUCCESS, paid_at__year=year, paid_at__month=month,
            ).aggregate(total=Sum('amount'))['total'] or 0
            monthly_labels.append(date(year, month, 1).strftime('%b'))
            monthly_totals.append(float(total))

        by_plan = Payment.objects.filter(status=Payment.Status.SUCCESS).values(
            'subscription__plan__tier',
        ).annotate(total=Sum('amount')).order_by('-total')

        context.update({
            'monthly_labels': monthly_labels,
            'monthly_totals': monthly_totals,
            'by_plan': by_plan,
            'total_revenue': Payment.objects.filter(status=Payment.Status.SUCCESS).aggregate(
                total=Sum('amount'),
            )['total'] or 0,
        })
        return context


# ---------------------------------------------------------------------------
# System management
# ---------------------------------------------------------------------------

class PlatformSettingsView(SuperAdminRequiredMixin, UpdateView):
    form_class = PlatformSettingsForm
    template_name = 'dashboard/settings_form.html'
    success_url = reverse_lazy('dashboard:settings')

    def get_object(self, queryset=None):
        return PlatformSettings.load()

    def form_valid(self, form):
        messages.success(self.request, 'Platform settings updated.')
        return super().form_valid(form)


class DatabaseBackupView(SuperAdminRequiredMixin, View):
    def get(self, request):
        db = settings.DATABASES['default']
        env = os.environ.copy()
        env['PGPASSWORD'] = db['PASSWORD']
        command = [
            settings.PG_DUMP_PATH,
            '-h', db['HOST'], '-p', str(db['PORT']), '-U', db['USER'],
            '-F', 'c', '-d', db['NAME'],
        ]
        try:
            result = subprocess.run(command, env=env, capture_output=True, check=True, timeout=120)
        except subprocess.CalledProcessError as exc:
            messages.error(request, f'Backup failed: {exc.stderr.decode(errors="replace")}')
            return redirect('dashboard:system_settings')
        except (subprocess.SubprocessError, FileNotFoundError) as exc:
            messages.error(request, f'Backup failed: {exc}')
            return redirect('dashboard:system_settings')

        filename = f'queueless-backup-{timezone.localdate().isoformat()}.dump'
        response = HttpResponse(result.stdout, content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class AnnouncementView(SuperAdminRequiredMixin, View):
    template_name = 'dashboard/announcement_form.html'

    def get(self, request):
        return render(request, self.template_name, {'form': AnnouncementForm()})

    def post(self, request):
        form = AnnouncementForm(request.POST)
        if form.is_valid():
            audience = form.cleaned_data['audience']
            recipients = User.objects.filter(is_active=True)
            if audience != 'all':
                recipients = recipients.filter(role=audience)

            Notification.objects.bulk_create([
                Notification(
                    user=recipient,
                    notification_type=Notification.NotificationType.GENERAL,
                    title=form.cleaned_data['title'],
                    message=form.cleaned_data['message'],
                )
                for recipient in recipients
            ])
            log_activity(
                ActivityLog.Action.ANNOUNCEMENT_SENT,
                f'"{form.cleaned_data["title"]}" to {recipients.count()} users',
                actor=request.user, request=request,
            )
            messages.success(request, f'Announcement sent to {recipients.count()} users.')
            return redirect('dashboard:announcement')
        return render(request, self.template_name, {'form': form})


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

class AnalyticsView(SuperAdminRequiredMixin, TemplateView):
    template_name = 'dashboard/analytics.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()

        usage_labels, usage_counts = [], []
        for offset in range(13, -1, -1):
            day = today - timedelta(days=offset)
            usage_labels.append(day.strftime('%b %d'))
            usage_counts.append(Token.objects.filter(queue__queue_date=day).count())

        growth_labels, growth_counts = [], []
        for offset in range(13, -1, -1):
            day = today - timedelta(days=offset)
            growth_labels.append(day.strftime('%b %d'))
            growth_counts.append(
                User.objects.filter(role=User.Role.CUSTOMER, date_joined__date=day).count(),
            )

        top_organizations = Organization.objects.annotate(
            token_count=Count('services__queues__tokens'),
        ).order_by('-token_count')[:5]

        top_services = Service.objects.annotate(
            token_count=Count('queues__tokens'),
        ).select_related('organization').order_by('-token_count')[:5]

        context.update({
            'usage_labels': usage_labels,
            'usage_counts': usage_counts,
            'growth_labels': growth_labels,
            'growth_counts': growth_counts,
            'top_organizations': top_organizations,
            'top_services': top_services,
        })
        return context


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

class ActivityLogListView(SuperAdminRequiredMixin, ListView):
    template_name = 'dashboard/activity_log.html'
    context_object_name = 'logs'
    paginate_by = 40

    def get_queryset(self):
        queryset = ActivityLog.objects.select_related('actor')
        action = self.request.GET.get('action', '')
        if action in dict(ActivityLog.Action.choices):
            queryset = queryset.filter(action=action)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['selected_action'] = self.request.GET.get('action', '')
        context['action_choices'] = ActivityLog.Action.choices
        return context
