from django.conf import settings
from django.db import models

from core.models import BaseModel


class CustomerProfile(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='customer_profile',
    )
    notify_by_email = models.BooleanField(default=True)
    notify_by_sms = models.BooleanField(default=False)
    preferred_language = models.CharField(max_length=10, default='en')

    def __str__(self):
        return f'Customer profile — {self.user}'
