from django.urls import path

from . import views

app_name = 'organizations'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),

    path('profile/', views.OrganizationProfileView.as_view(), name='profile'),
    path('settings/', views.OrganizationSettingsView.as_view(), name='settings'),

    path('departments/', views.DepartmentListView.as_view(), name='departments'),
    path('departments/<uuid:pk>/edit/', views.DepartmentUpdateView.as_view(), name='department_edit'),
    path('departments/<uuid:pk>/delete/', views.DepartmentDeleteView.as_view(), name='department_delete'),

    path('services/', views.ServiceListView.as_view(), name='services'),
    path('services/add/', views.ServiceCreateView.as_view(), name='service_add'),
    path('services/<uuid:pk>/edit/', views.ServiceUpdateView.as_view(), name='service_edit'),
    path('services/<uuid:pk>/delete/', views.ServiceDeleteView.as_view(), name='service_delete'),

    path('queues/', views.QueueListView.as_view(), name='queues'),
    path('queues/add/', views.QueueCreateView.as_view(), name='queue_add'),
    path('queues/<uuid:pk>/edit/', views.QueueUpdateView.as_view(), name='queue_edit'),
    path('queues/<uuid:pk>/delete/', views.QueueDeleteView.as_view(), name='queue_delete'),

    path('staff/', views.StaffListView.as_view(), name='staff_list'),
    path('staff/add/', views.StaffCreateView.as_view(), name='staff_add'),
    path('staff/<uuid:pk>/edit/', views.StaffUpdateView.as_view(), name='staff_edit'),
    path('staff/<uuid:pk>/remove/', views.StaffRemoveView.as_view(), name='staff_remove'),

    path('reports/', views.ReportsView.as_view(), name='reports'),
    path('reports/export.pdf', views.ReportsPDFExportView.as_view(), name='reports_pdf'),
]
