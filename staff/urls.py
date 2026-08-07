from django.urls import path

from . import views

app_name = 'staff'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('book-token/', views.BookTokenView.as_view(), name='book_token'),
    path('queues/<uuid:pk>/', views.QueueWorkView.as_view(), name='queue_work'),
    path('queues/<uuid:pk>/call-next/', views.CallNextView.as_view(), name='call_next'),

    path('tokens/<uuid:pk>/start-service/', views.StartServiceView.as_view(), name='start_service'),
    path('tokens/<uuid:pk>/skip/', views.SkipTokenView.as_view(), name='skip_token'),
    path('tokens/<uuid:pk>/recall/', views.RecallTokenView.as_view(), name='recall_token'),
    path('tokens/<uuid:pk>/complete/', views.CompleteTokenView.as_view(), name='complete_token'),
    path('tokens/<uuid:pk>/cancel/', views.CancelTokenView.as_view(), name='cancel_token'),
    path('tokens/<uuid:pk>/transfer/', views.TransferTokenView.as_view(), name='transfer_token'),
    path('tokens/<uuid:pk>/receipt.pdf', views.TokenReceiptPDFView.as_view(), name='token_receipt_pdf'),

    path('reports/', views.ReportsView.as_view(), name='reports'),
]
