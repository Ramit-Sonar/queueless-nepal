from django.urls import path

from . import views

app_name = 'qr_generator'

urlpatterns = [
    path('', views.QRGeneratorView.as_view(), name='generate'),
    path('image.png', views.QRImageView.as_view(), name='image'),
]
