from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.PlatformDashboardView.as_view(), name='platform_dashboard'),

    path('organizations/', views.OrganizationListView.as_view(), name='organizations'),
    path('organizations/add/', views.OrganizationCreateView.as_view(), name='organization_add'),
    path('organizations/<uuid:pk>/edit/', views.OrganizationUpdateView.as_view(), name='organization_edit'),
    path('organizations/<uuid:pk>/approve/', views.OrganizationApproveView.as_view(), name='organization_approve'),
    path('organizations/<uuid:pk>/suspend/', views.OrganizationSuspendView.as_view(), name='organization_suspend'),
    path('organizations/<uuid:pk>/delete/', views.OrganizationDeleteView.as_view(), name='organization_delete'),

    path('users/', views.UserListView.as_view(), name='users'),
    path('users/export.csv', views.UserExportCSVView.as_view(), name='user_export_csv'),
    path('users/export.pdf', views.UserExportPDFView.as_view(), name='user_export_pdf'),
    path('users/bulk-action/', views.UserBulkActionView.as_view(), name='user_bulk_action'),
    path('users/<uuid:pk>/detail.json', views.UserDetailJSONView.as_view(), name='user_detail_json'),
    path('users/<uuid:pk>/block/', views.UserBlockView.as_view(), name='user_block'),
    path('users/<uuid:pk>/reset-password/', views.UserResetPasswordView.as_view(), name='user_reset_password'),

    path('subscriptions/', views.SubscriptionListView.as_view(), name='subscriptions'),
    path('subscriptions/plans/<uuid:pk>/edit/', views.PlanUpdateView.as_view(), name='plan_edit'),
    path('subscriptions/assign/<uuid:org_pk>/', views.SubscriptionAssignView.as_view(), name='subscription_assign'),
    path('subscriptions/<uuid:pk>/renew/', views.RenewSubscriptionView.as_view(), name='subscription_renew'),

    path('payments/', views.PaymentListView.as_view(), name='payments'),
    path('payments/add/', views.PaymentCreateView.as_view(), name='payment_add'),
    path('payments/<uuid:pk>/invoice.pdf', views.PaymentInvoicePDFView.as_view(), name='payment_invoice'),
    path('payments/revenue/', views.RevenueReportView.as_view(), name='revenue_report'),

    path('system/settings/', views.PlatformSettingsView.as_view(), name='system_settings'),
    path('system/backup/', views.DatabaseBackupView.as_view(), name='system_backup'),
    path('system/announcement/', views.AnnouncementView.as_view(), name='announcement'),

    path('analytics/', views.AnalyticsView.as_view(), name='analytics'),
    path('activity/', views.ActivityLogListView.as_view(), name='activity_log'),
]
