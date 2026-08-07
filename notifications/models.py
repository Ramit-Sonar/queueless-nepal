from django.conf import settings
from django.db import models

from core.models import BaseModel
from queue_management.models import Token


class Notification(BaseModel):
    class NotificationType(models.TextChoices):
        TOKEN_CALLED = 'token_called', 'Token Called'
        TOKEN_COMPLETED = 'token_completed', 'Service Completed'
        QUEUE_UPDATE = 'queue_update', 'Queue Update'
        GENERAL = 'general', 'General'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    notification_type = models.CharField(
        max_length=20, choices=NotificationType.choices, default=NotificationType.GENERAL,
    )
    title = models.CharField(max_length=150)
    message = models.CharField(max_length=255)
    related_token = models.ForeignKey(
        Token,
        on_delete=models.CASCADE,
        related_name='notifications',
        null=True,
        blank=True,
    )
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
        ]

    def __str__(self):
        return f'{self.title} → {self.user}'
