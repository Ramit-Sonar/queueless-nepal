import io

from django.contrib import messages
from django.db.models import Avg, DurationField, ExpressionWrapper, F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, TemplateView

from queue_management.models import Queue, Token

from .forms import TransferForm, WalkInBookingForm
from .mixins import StaffRequiredMixin


class DashboardView(StaffRequiredMixin, TemplateView):
    template_name = 'staff/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queues = Queue.objects.filter(
            service__organization=self.organization,
            queue_date=timezone.localdate(),
            status=Queue.Status.OPEN,
        ).select_related('service')
        if self.staff_profile.department_id:
            queues = queues.filter(service__department_id=self.staff_profile.department_id)
        context['queues'] = queues.order_by('service__name')
        context['staff_profile'] = self.staff_profile
        return context


class BookTokenView(StaffRequiredMixin, View):
    template_name = 'staff/book_token.html'

    def _locked_service(self):
        service = self.staff_profile.service
        if service is not None and service.organization_id == self.organization.id and service.is_active:
            return service
        return None

    def _service_queryset(self):
        services = self.organization.services.filter(is_active=True)
        if self.staff_profile.department_id:
            services = services.filter(department_id=self.staff_profile.department_id)
        return services.order_by('name')

    def _build_form(self, data=None):
        return WalkInBookingForm(
            data,
            service_queryset=self._service_queryset(),
            locked_service=self._locked_service(),
        )

    def get(self, request):
        return render(request, self.template_name, {
            'form': self._build_form(),
            'staff_profile': self.staff_profile,
            'locked_service': self._locked_service(),
        })

    def post(self, request):
        form = self._build_form(request.POST)
        locked_service = self._locked_service()

        if not form.is_valid():
            return render(request, self.template_name, {
                'form': form, 'staff_profile': self.staff_profile, 'locked_service': locked_service,
            })

        service = form.cleaned_data['service']
        customer, created = form.get_or_create_customer()
        queue = Queue.get_or_create_today(service)

        existing_token = Token.objects.filter(
            queue=queue, customer=customer, status__in=Token.ACTIVE_STATUSES,
        ).first()
        if existing_token:
            messages.info(
                request,
                f'{customer.get_full_name() or customer.username} already has an active token for '
                f'{service.name} today: {existing_token.display_number}.',
            )
            return redirect('staff:queue_work', pk=queue.pk)

        active_count = Token.objects.filter(
            queue__service__organization=self.organization,
            customer=customer,
            status__in=Token.ACTIVE_STATUSES,
        ).count()
        if active_count >= self.organization.max_active_tokens_per_customer:
            messages.error(
                request,
                f'{customer.get_full_name() or customer.username} already has the maximum of '
                f'{self.organization.max_active_tokens_per_customer} active token(s) at {self.organization.name}.',
            )
            return render(request, self.template_name, {
                'form': form, 'staff_profile': self.staff_profile, 'locked_service': locked_service,
            })

        token = queue.issue_token(customer=customer)
        new_account_note = ' (new customer account created)' if created else ''
        messages.success(
            request,
            f'Token {token.display_number} booked for {customer.get_full_name() or customer.username}{new_account_note}.',
        )
        return redirect('staff:queue_work', pk=queue.pk)


class QueueWorkView(StaffRequiredMixin, DetailView):
    model = Queue
    template_name = 'staff/queue_work.html'
    context_object_name = 'queue'

    def get_queryset(self):
        return Queue.objects.filter(service__organization=self.organization).select_related('service')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queue = self.object
        current_token = queue.currently_serving
        today_tokens = queue.tokens.all()

        context.update({
            'current_token': current_token,
            'waiting_tokens': queue.waiting_tokens[:5],
            'waiting_count': queue.waiting_tokens.count(),
            'skipped_tokens': queue.skipped_tokens,
            'completed_tokens': queue.completed_tokens_today,
            'recent_visits': None,
            'forward_form': None,
        })

        duration_stats = today_tokens.filter(
            status=Token.Status.COMPLETED, started_at__isnull=False,
        ).annotate(
            service_duration=ExpressionWrapper(F('completed_at') - F('started_at'), output_field=DurationField()),
        ).aggregate(avg_duration=Avg('service_duration'))
        avg_service_minutes = (
            round(duration_stats['avg_duration'].total_seconds() / 60, 1)
            if duration_stats['avg_duration'] else 0
        )
        context['stats'] = {
            'total': today_tokens.count(),
            'waiting': context['waiting_count'],
            'called': today_tokens.filter(status=Token.Status.CALLED).count(),
            'serving': today_tokens.filter(status=Token.Status.SERVING).count(),
            'completed': today_tokens.filter(status=Token.Status.COMPLETED).count(),
            'skipped': today_tokens.filter(status=Token.Status.SKIPPED).count(),
            'cancelled': today_tokens.filter(status=Token.Status.CANCELLED).count(),
            'avg_service_minutes': avg_service_minutes,
        }

        if current_token:
            context['recent_visits'] = Token.objects.filter(
                customer=current_token.customer,
                queue__service__organization=self.organization,
            ).exclude(pk=current_token.pk).select_related('queue__service').order_by('-created_at')[:5]
            context['forward_form'] = TransferForm(organization=self.organization, exclude_service=queue.service)
            context['service_journey'] = current_token.service_journey
        return context


def _auto_call_next(queue):
    """Called after a token leaves the counter (completed/skipped/cancelled/forwarded) so
    staff don't need an extra click to bring up the next waiting customer."""
    next_token = queue.waiting_tokens.first()
    if next_token:
        next_token.mark_called()
    return next_token


class StartServiceView(StaffRequiredMixin, View):
    def post(self, request, pk):
        token = get_object_or_404(Token, pk=pk, queue__service__organization=self.organization)
        if token.status != Token.Status.CALLED:
            messages.error(request, 'Only a called customer can start service.')
            return redirect('staff:queue_work', pk=token.queue_id)
        token.mark_serving(staff=request.user)
        messages.success(request, f'Service started for {token.display_number}.')
        return redirect('staff:queue_work', pk=token.queue_id)


class CallNextView(StaffRequiredMixin, View):
    def post(self, request, pk):
        queue = get_object_or_404(Queue, pk=pk, service__organization=self.organization)
        if queue.currently_serving:
            messages.error(request, 'Finish or skip the current customer before calling the next one.')
            return redirect('staff:queue_work', pk=queue.pk)

        next_token = queue.waiting_tokens.first()
        if not next_token:
            messages.info(request, 'No customers waiting in this queue.')
            return redirect('staff:queue_work', pk=queue.pk)

        next_token.mark_called()
        messages.success(request, f'Called {next_token.display_number}.')
        return redirect('staff:queue_work', pk=queue.pk)


class SkipTokenView(StaffRequiredMixin, View):
    def post(self, request, pk):
        token = get_object_or_404(Token, pk=pk, queue__service__organization=self.organization)
        if token.status != Token.Status.CALLED:
            messages.error(request, 'Only a called customer can be skipped.')
            return redirect('staff:queue_work', pk=token.queue_id)
        reason = request.POST.get('reason', '').strip()
        if reason:
            token.notes = reason
            token.save(update_fields=['notes'])
        token.mark_skipped()
        next_token = _auto_call_next(token.queue)
        if next_token:
            messages.info(request, f'{token.display_number} skipped. Now calling {next_token.display_number}.')
        else:
            messages.info(request, f'{token.display_number} skipped.')
        return redirect('staff:queue_work', pk=token.queue_id)


class RecallTokenView(StaffRequiredMixin, View):
    def post(self, request, pk):
        token = get_object_or_404(
            Token, pk=pk, queue__service__organization=self.organization, status=Token.Status.SKIPPED,
        )
        if token.queue.currently_serving:
            messages.error(request, 'Finish or skip the current customer before recalling another.')
            return redirect('staff:queue_work', pk=token.queue_id)

        token.mark_called()
        messages.success(request, f'{token.display_number} recalled.')
        return redirect('staff:queue_work', pk=token.queue_id)


class CompleteTokenView(StaffRequiredMixin, View):
    def post(self, request, pk):
        token = get_object_or_404(Token, pk=pk, queue__service__organization=self.organization)
        if token.status != Token.Status.SERVING:
            messages.error(request, 'Start service before completing this token.')
            return redirect('staff:queue_work', pk=token.queue_id)
        remarks = request.POST.get('remarks', '').strip()
        if remarks:
            token.notes = remarks
            token.save(update_fields=['notes'])
        token.mark_completed(staff=request.user)
        next_token = _auto_call_next(token.queue)
        if next_token:
            messages.success(request, f'{token.display_number} marked complete. Now calling {next_token.display_number}.')
        else:
            messages.success(request, f'{token.display_number} marked complete.')
        return redirect('staff:queue_work', pk=token.queue_id)


class CancelTokenView(StaffRequiredMixin, View):
    def post(self, request, pk):
        token = get_object_or_404(Token, pk=pk, queue__service__organization=self.organization)
        if token.status not in Token.ACTIVE_STATUSES:
            messages.error(request, 'This token can no longer be cancelled.')
            return redirect('staff:queue_work', pk=token.queue_id)
        reason = request.POST.get('reason', '').strip()
        if reason:
            token.notes = reason
            token.save(update_fields=['notes'])
        was_current = token.status in (Token.Status.CALLED, Token.Status.SERVING)
        token.cancel()
        if was_current:
            next_token = _auto_call_next(token.queue)
            if next_token:
                messages.success(request, f'{token.display_number} cancelled. Now calling {next_token.display_number}.')
            else:
                messages.success(request, f'{token.display_number} cancelled.')
        else:
            messages.success(request, f'{token.display_number} cancelled.')
        return redirect('staff:queue_work', pk=token.queue_id)


class TransferTokenView(StaffRequiredMixin, View):
    def post(self, request, pk):
        token = get_object_or_404(Token, pk=pk, queue__service__organization=self.organization)
        old_queue_id = token.queue_id

        if token.status != Token.Status.SERVING:
            messages.error(request, 'Start service before forwarding this token.')
            return redirect('staff:queue_work', pk=old_queue_id)

        form = TransferForm(request.POST, organization=self.organization, exclude_service=token.queue.service)
        if not form.is_valid():
            messages.error(request, 'Please choose a valid service to forward to.')
            return redirect('staff:queue_work', pk=old_queue_id)

        new_service = form.cleaned_data['service']
        reason = form.cleaned_data.get('reason', '').strip()
        priority = form.cleaned_data.get('priority') or Token.Priority.NORMAL

        token.notes = f'Completed & forwarded to {new_service.name}' + (f' — {reason}' if reason else '')
        token.save(update_fields=['notes'])
        token.mark_completed(staff=request.user)

        new_queue = Queue.get_or_create_today(new_service)
        new_token = new_queue.issue_token(customer=token.customer)
        new_token.transferred_from = token
        new_token.priority = priority
        new_token.save(update_fields=['transferred_from', 'priority'])

        next_token = _auto_call_next(token.queue)
        if next_token:
            messages.success(
                request,
                f'Completed & forwarded to {new_service.name} as {new_token.display_number}. '
                f'Now calling {next_token.display_number}.',
            )
        else:
            messages.success(request, f'Completed & forwarded to {new_service.name} as {new_token.display_number}.')
        return redirect('staff:queue_work', pk=old_queue_id)


class TokenReceiptPDFView(StaffRequiredMixin, View):
    def get(self, request, pk):
        from reportlab.lib.pagesizes import A6
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        token = get_object_or_404(
            Token.objects.select_related('queue__service__organization', 'queue__service__department'),
            pk=pk, queue__service__organization=self.organization,
        )
        styles = getSampleStyleSheet()
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A6, title=f'Token {token.display_number}', topMargin=20, bottomMargin=20)
        elements = [
            Paragraph('QueueLess Nepal', styles['Heading3']),
            Paragraph(self.organization.name, styles['Normal']),
            Spacer(1, 10),
            Paragraph(token.display_number, styles['Title']),
            Spacer(1, 6),
            Paragraph(token.queue.service.name, styles['Normal']),
        ]
        if token.queue.service.department:
            elements.append(Paragraph(token.queue.service.department.name, styles['Normal']))
        elements += [
            Spacer(1, 10),
            Paragraph(f'Customer: {token.customer.get_full_name() or token.customer.username}', styles['Normal']),
            Paragraph(f'Status: {token.get_status_display()}', styles['Normal']),
            Paragraph(f'Booked: {timezone.localtime(token.created_at).strftime("%b %d, %Y %I:%M %p")}', styles['Normal']),
            Paragraph(f'Reference: {str(token.pk)[:8].upper()}', styles['Normal']),
        ]
        if token.notes:
            elements.append(Paragraph(f'Notes: {token.notes}', styles['Normal']))
        doc.build(elements)
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{token.display_number}-receipt.pdf"'
        return response


class ReportsView(StaffRequiredMixin, TemplateView):
    template_name = 'staff/reports.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()

        my_completed_today = Token.objects.filter(
            served_by=self.request.user,
            status=Token.Status.COMPLETED,
            completed_at__date=today,
        ).select_related('queue__service', 'customer')

        duration_stats = my_completed_today.filter(called_at__isnull=False).annotate(
            service_duration=ExpressionWrapper(F('completed_at') - F('called_at'), output_field=DurationField()),
        ).aggregate(avg_duration=Avg('service_duration'))
        avg_minutes = (
            round(duration_stats['avg_duration'].total_seconds() / 60, 1)
            if duration_stats['avg_duration'] else 0
        )

        pending_qs = Token.objects.filter(
            queue__service__organization=self.organization,
            queue__queue_date=today,
            status=Token.Status.WAITING,
        )
        if self.staff_profile.department_id:
            pending_qs = pending_qs.filter(queue__service__department_id=self.staff_profile.department_id)

        context.update({
            'completed_today_count': my_completed_today.count(),
            'avg_service_minutes': avg_minutes,
            'pending_count': pending_qs.count(),
            'completed_today': my_completed_today.order_by('-completed_at'),
        })
        return context
