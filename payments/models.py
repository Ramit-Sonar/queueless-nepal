import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import BaseModel
from subscriptions.models import Subscription


def generate_transaction_id():
    return f'TXN-{uuid.uuid4().hex[:12].upper()}'


class Payment(BaseModel):
    class Provider(models.TextChoices):
        ESEWA = 'esewa', 'eSewa'
        KHALTI = 'khalti', 'Khalti'
        BANK_TRANSFER = 'bank_transfer', 'Bank Transfer'
        CASH = 'cash', 'Cash'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        SUCCESS = 'success', 'Success'
        PENDING = 'pending', 'Pending'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'

    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.OTHER)
    transaction_id = models.CharField(max_length=40, unique=True, default=generate_transaction_id)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUCCESS)
    paid_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='recorded_payments',
        null=True,
        blank=True,
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-paid_at']
        indexes = [
            models.Index(fields=['status', '-paid_at']),
        ]

    def __str__(self):
        return f'{self.transaction_id} — {self.subscription.organization.name}'
