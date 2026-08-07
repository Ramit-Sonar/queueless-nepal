import io
from datetime import date, timedelta

from django.contrib import messages
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, TemplateView, UpdateView

from queue_management.models import Queue, Token
from services.models import Service
from staff.models import StaffProfile

from .forms import (
    DepartmentForm,
    OrganizationProfileForm,
    OrganizationSettingsForm,
    QueueCreateForm,
    QueueEditForm,
    ServiceForm,
    StaffCreateForm,
    StaffProfileFieldsForm,
    StaffUserFieldsForm,
)
from .mixins import OrgAdminRequiredMixin
from .models import Department


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class DashboardView(OrgAdminRequiredMixin, TemplateView):
    template_name = 'organizations/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        organization = self.organization
        today = timezone.localdate()

        todays_queues = Queue.objects.filter(
            service__organization=organization, queue_date=today,
        ).select_related('service')
        todays_tokens = Token.objects.filter(queue__in=todays_queues)

        trend_labels, trend_counts = [], []
        for offset in range(6, -1, -1):
            day = today - timedelta(days=offset)
            trend_labels.append(day.strftime('%a'))
            trend_counts.append(
                Token.objects.filter(queue__service__organization=organization, queue__queue_date=day).count(),
            )

        context.update({
            'organization': organization,
            'stats': {
                'booked_today': todays_tokens.count(),
                'completed_today': todays_tokens.filter(status=Token.Status.COMPLETED).count(),
                'cancelled_today': todays_tokens.filter(status=Token.Status.CANCELLED).count(),
                'active_queues': todays_queues.filter(status=Queue.Status.OPEN).count(),
                'total_customers': Token.objects.filter(
                    queue__service__organization=organization,
                ).values('customer').distinct().count(),
                'total_staff': StaffProfile.objects.filter(organization=organization, is_active=True).count(),
                'total_services': organization.services.filter(is_active=True).count(),
            },
            'active_queues': todays_queues.order_by('service__name'),
            'trend_labels': trend_labels,
            'trend_counts': trend_counts,
        })
        return context


# ---------------------------------------------------------------------------
# Organization profile & settings
# ---------------------------------------------------------------------------

class OrganizationProfileView(OrgAdminRequiredMixin, UpdateView):
    form_class = OrganizationProfileForm
    template_name = 'organizations/profile_form.html'
    success_url = reverse_lazy('organizations:profile')

    def get_object(self, queryset=None):
        return self.organization

    def form_valid(self, form):
        messages.success(self.request, 'Organization profile updated.')
        return super().form_valid(form)


class OrganizationSettingsView(OrgAdminRequiredMixin, UpdateView):
    form_class = OrganizationSettingsForm
    template_name = 'organizations/settings_form.html'
    success_url = reverse_lazy('organizations:settings')

    def get_object(self, queryset=None):
        return self.organization

    def form_valid(self, form):
        messages.success(self.request, 'Settings updated.')
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------

class DepartmentListView(OrgAdminRequiredMixin, ListView):
    template_name = 'organizations/department_list.html'
    context_object_name = 'departments'

    def get_queryset(self):
        return Department.objects.filter(organization=self.organization)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['organization'] = self.organization
        context.setdefault('form', DepartmentForm())
        return context

    def post(self, request, *args, **kwargs):
        form = DepartmentForm(request.POST)
        if form.is_valid():
            department = form.save(commit=False)
            department.organization = self.organization
            department.save()
            messages.success(request, f'Department "{department.name}" added.')
            return redirect('organizations:departments')
        self.object_list = self.get_queryset()
        return self.render_to_response(self.get_context_data(form=form))


class DepartmentUpdateView(OrgAdminRequiredMixin, View):
    def get_object(self):
        return get_object_or_404(Department, pk=self.kwargs['pk'], organization=self.organization)

    def post(self, request, pk):
        department = self.get_object()
        form = DepartmentForm(request.POST, instance=department)
        if form.is_valid():
            form.save()
            messages.success(request, 'Department updated.')
        else:
            messages.error(request, 'Could not update department — please check the form.')
        return redirect('organizations:departments')


class DepartmentDeleteView(OrgAdminRequiredMixin, View):
    def post(self, request, pk):
        department = get_object_or_404(Department, pk=pk, organization=self.organization)
        if department.services.exists():
            messages.error(request, 'Cannot delete a department that still has services. Reassign them first.')
        else:
            department.delete()
            messages.success(request, 'Department deleted.')
        return redirect('organizations:departments')


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

class ServiceListView(OrgAdminRequiredMixin, ListView):
    template_name = 'organizations/service_list.html'
    context_object_name = 'services'

    def get_queryset(self):
        return Service.objects.filter(organization=self.organization).select_related('department')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['organization'] = self.organization
        return context


class ServiceCreateView(OrgAdminRequiredMixin, View):
    template_name = 'organizations/service_form.html'

    def get(self, request):
        form = ServiceForm(organization=self.organization)
        return render(request, self.template_name, {'form': form, 'organization': self.organization, 'mode': 'create'})

    def post(self, request):
        form = ServiceForm(request.POST, organization=self.organization)
        if form.is_valid():
            service = form.save(commit=False)
            service.organization = self.organization
            service.save()
            messages.success(request, f'Service "{service.name}" created.')
            return redirect('organizations:services')
        return render(request, self.template_name, {'form': form, 'organization': self.organization, 'mode': 'create'})


class ServiceUpdateView(OrgAdminRequiredMixin, View):
    template_name = 'organizations/service_form.html'

    def get_object(self):
        return get_object_or_404(Service, pk=self.kwargs['pk'], organization=self.organization)

    def get(self, request, pk):
        service = self.get_object()
        form = ServiceForm(instance=service, organization=self.organization)
        return render(request, self.template_name, {'form': form, 'organization': self.organization, 'mode': 'edit', 'service': service})

    def post(self, request, pk):
        service = self.get_object()
        form = ServiceForm(request.POST, instance=service, organization=self.organization)
        if form.is_valid():
            form.save()
            messages.success(request, 'Service updated.')
            return redirect('organizations:services')
        return render(request, self.template_name, {'form': form, 'organization': self.organization, 'mode': 'edit', 'service': service})


class ServiceDeleteView(OrgAdminRequiredMixin, View):
    def post(self, request, pk):
        service = get_object_or_404(Service, pk=pk, organization=self.organization)
        if service.queues.exists():
            messages.error(request, 'This service already has queue history — deactivate it instead of deleting.')
        else:
            service.delete()
            messages.success(request, 'Service deleted.')
        return redirect('organizations:services')


# ---------------------------------------------------------------------------
# Queues
# ---------------------------------------------------------------------------

class QueueListView(OrgAdminRequiredMixin, ListView):
    template_name = 'organizations/queue_list.html'
    context_object_name = 'queues'

    def get_queryset(self):
        return Queue.objects.filter(
            service__organization=self.organization,
        ).select_related('service').order_by('-queue_date', 'service__name')[:40]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['organization'] = self.organization
        return context


class QueueCreateView(OrgAdminRequiredMixin, View):
    template_name = 'organizations/queue_form.html'

    def get(self, request):
        form = QueueCreateForm(organization=self.organization)
        return render(request, self.template_name, {'form': form, 'organization': self.organization})

    def post(self, request):
        form = QueueCreateForm(request.POST, organization=self.organization)
        if form.is_valid():
            service = form.cleaned_data['service']
            queue, created = Queue.objects.get_or_create(service=service, queue_date=timezone.localdate())
            if created:
                messages.success(request, f'Queue opened for {service.name}.')
            else:
                messages.info(request, f'{service.name} already has a queue open today.')
            return redirect('organizations:queue_edit', pk=queue.pk)
        return render(request, self.template_name, {'form': form, 'organization': self.organization})


class QueueUpdateView(OrgAdminRequiredMixin, UpdateView):
    form_class = QueueEditForm
    template_name = 'organizations/queue_edit.html'
    success_url = reverse_lazy('organizations:queues')

    def get_queryset(self):
        return Queue.objects.filter(service__organization=self.organization)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['organization'] = self.organization
        context['tokens'] = self.object.tokens.select_related('customer').order_by('token_number')
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Queue updated.')
        return super().form_valid(form)


class QueueDeleteView(OrgAdminRequiredMixin, View):
    def post(self, request, pk):
        queue = get_object_or_404(Queue, pk=pk, service__organization=self.organization)
        if queue.tokens.exists():
            messages.error(request, 'Cannot delete a queue that already has tokens — close it instead.')
        else:
            queue.delete()
            messages.success(request, 'Queue deleted.')
        return redirect('organizations:queues')


# ---------------------------------------------------------------------------
# Staff
# ---------------------------------------------------------------------------

class StaffListView(OrgAdminRequiredMixin, ListView):
    template_name = 'organizations/staff_list.html'
    context_object_name = 'staff_members'

    def get_queryset(self):
        return StaffProfile.objects.filter(organization=self.organization).select_related('user', 'department')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['organization'] = self.organization
        return context


class StaffCreateView(OrgAdminRequiredMixin, View):
    template_name = 'organizations/staff_form.html'

    def get(self, request):
        form = StaffCreateForm(organization=self.organization)
        return render(request, self.template_name, {'form': form, 'organization': self.organization, 'mode': 'create'})

    def post(self, request):
        form = StaffCreateForm(request.POST, organization=self.organization)
        if form.is_valid():
            staff_user = form.save()
            messages.success(request, f'{staff_user.get_full_name()} added to staff.')
            return redirect('organizations:staff_list')
        return render(request, self.template_name, {'form': form, 'organization': self.organization, 'mode': 'create'})


class StaffUpdateView(OrgAdminRequiredMixin, View):
    template_name = 'organizations/staff_form.html'

    def get_object(self):
        return get_object_or_404(StaffProfile, pk=self.kwargs['pk'], organization=self.organization)

    def get(self, request, pk):
        staff = self.get_object()
        user_form = StaffUserFieldsForm(instance=staff.user)
        profile_form = StaffProfileFieldsForm(instance=staff, organization=self.organization)
        return render(request, self.template_name, {
            'user_form': user_form, 'profile_form': profile_form,
            'staff': staff, 'organization': self.organization, 'mode': 'edit',
        })

    def post(self, request, pk):
        staff = self.get_object()
        user_form = StaffUserFieldsForm(request.POST, instance=staff.user)
        profile_form = StaffProfileFieldsForm(request.POST, instance=staff, organization=self.organization)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile = profile_form.save()
            profile.user.is_active = profile.is_active
            profile.user.save(update_fields=['is_active'])
            messages.success(request, 'Staff member updated.')
            return redirect('organizations:staff_list')
        return render(request, self.template_name, {
            'user_form': user_form, 'profile_form': profile_form,
            'staff': staff, 'organization': self.organization, 'mode': 'edit',
        })


class StaffRemoveView(OrgAdminRequiredMixin, View):
    def post(self, request, pk):
        staff = get_object_or_404(StaffProfile, pk=pk, organization=self.organization)
        staff.is_active = False
        staff.save(update_fields=['is_active'])
        staff.user.is_active = False
        staff.user.save(update_fields=['is_active'])
        messages.success(request, f'{staff.user.get_full_name() or staff.user.username} removed from staff.')
        return redirect('organizations:staff_list')


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def _resolve_period(request):
    today = timezone.localdate()
    period = request.GET.get('period', 'today')
    if period == 'week':
        start, end = today - timedelta(days=today.weekday()), today
    elif period == 'month':
        start, end = today.replace(day=1), today
    elif period == 'custom':
        try:
            start = date.fromisoformat(request.GET.get('start', ''))
            end = date.fromisoformat(request.GET.get('end', ''))
        except ValueError:
            start, end, period = today, today, 'today'
    else:
        start, end, period = today, today, 'today'
    return start, end, period


def _build_report_data(organization, request):
    start, end, period = _resolve_period(request)
    tokens = Token.objects.filter(
        queue__service__organization=organization,
        queue__queue_date__gte=start,
        queue__queue_date__lte=end,
    ).select_related('queue__service', 'customer', 'served_by')

    wait_stats = tokens.filter(called_at__isnull=False).annotate(
        wait_duration=ExpressionWrapper(F('called_at') - F('created_at'), output_field=DurationField()),
    ).aggregate(avg_wait=Avg('wait_duration'))
    avg_wait_minutes = round(wait_stats['avg_wait'].total_seconds() / 60, 1) if wait_stats['avg_wait'] else 0

    summary = {
        'total': tokens.count(),
        'completed': tokens.filter(status=Token.Status.COMPLETED).count(),
        'cancelled': tokens.filter(status=Token.Status.CANCELLED).count(),
        'no_show': tokens.filter(status=Token.Status.NO_SHOW).count(),
        'avg_wait_minutes': avg_wait_minutes,
    }

    service_breakdown = tokens.values('queue__service__name').annotate(
        total=Count('id'),
        completed=Count('id', filter=Q(status=Token.Status.COMPLETED)),
        cancelled=Count('id', filter=Q(status=Token.Status.CANCELLED)),
    ).order_by('-total')

    staff_performance = tokens.filter(served_by__isnull=False).values(
        'served_by__first_name', 'served_by__last_name', 'served_by__username',
    ).annotate(completed_count=Count('id', filter=Q(status=Token.Status.COMPLETED))).order_by('-completed_count')

    top_customers = tokens.values(
        'customer__first_name', 'customer__last_name', 'customer__username',
    ).annotate(visit_count=Count('id')).order_by('-visit_count')[:10]

    return {
        'start': start, 'end': end, 'period': period,
        'summary': summary,
        'service_breakdown': service_breakdown,
        'staff_performance': staff_performance,
        'top_customers': top_customers,
    }


class ReportsView(OrgAdminRequiredMixin, TemplateView):
    template_name = 'organizations/reports.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['organization'] = self.organization
        context.update(_build_report_data(self.organization, self.request))
        return context


class ReportsPDFExportView(OrgAdminRequiredMixin, View):
    def get(self, request):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        organization = self.organization
        data = _build_report_data(organization, request)
        styles = getSampleStyleSheet()

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, title=f'{organization.name} Report')
        elements = [
            Paragraph(f'{organization.name} — Queue Report', styles['Title']),
            Paragraph(f"{data['start']} to {data['end']}", styles['Normal']),
            Spacer(1, 16),
            Paragraph('Summary', styles['Heading2']),
        ]

        summary = data['summary']
        summary_table = Table([
            ['Total tokens', 'Completed', 'Cancelled', 'No show', 'Avg wait (min)'],
            [summary['total'], summary['completed'], summary['cancelled'], summary['no_show'], summary['avg_wait_minutes']],
        ])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563EB')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        elements += [summary_table, Spacer(1, 20), Paragraph('By Service', styles['Heading2'])]

        service_rows = [['Service', 'Total', 'Completed', 'Cancelled']]
        for row in data['service_breakdown']:
            service_rows.append([row['queue__service__name'], row['total'], row['completed'], row['cancelled']])
        if len(service_rows) == 1:
            service_rows.append(['No data for this period', '', '', ''])
        service_table = Table(service_rows)
        service_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))
        elements.append(service_table)

        doc.build(elements)
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/pdf')
        filename = f"{organization.slug}-report-{data['start']}-to-{data['end']}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
