from django.urls import path

from . import views

app_name = 'customers'

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),

    path('scan/', views.ScanQRView.as_view(), name='scan'),
    path('scan/lookup/', views.ScanLookupView.as_view(), name='scan_lookup'),

    path('organizations/', views.SelectOrganizationView.as_view(), name='select_organization'),
    path('organizations/<slug:slug>/services/', views.SelectServiceView.as_view(), name='select_service'),

    path('book/<uuid:service_id>/', views.BookTokenView.as_view(), name='book_token'),

    path('tokens/', views.TokenHistoryView.as_view(), name='token_history'),
    path('tokens/<uuid:pk>/', views.TokenDetailView.as_view(), name='token_detail'),
    path('tokens/<uuid:pk>/qr.png', views.TokenQRView.as_view(), name='token_qr'),
    path('tokens/<uuid:pk>/receipt.pdf', views.TokenPDFView.as_view(), name='token_pdf'),
    path('tokens/<uuid:pk>/status.json', views.TokenStatusJSONView.as_view(), name='token_status_json'),
    path('tokens/<uuid:pk>/cancel/', views.CancelTokenView.as_view(), name='cancel_token'),
    path('tokens/<uuid:pk>/rebook/', views.RebookTokenView.as_view(), name='rebook_token'),

    path('notifications/', views.NotificationListView.as_view(), name='notifications'),
]
