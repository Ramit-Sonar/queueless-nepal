import uuid

from django.conf import settings
from django.db import models


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class ActivityLog(BaseModel):
    class Action(models.TextChoices):
        LOGIN = 'login', 'Login'
        ORG_APPROVED = 'org_approved', 'Organization Approved'
        ORG_SUSPENDED = 'org_suspended', 'Organization Suspended'
        ORG_REACTIVATED = 'org_reactivated', 'Organization Reactivated'
        ORG_CREATED = 'org_created', 'Organization Created'
        ORG_DELETED = 'org_deleted', 'Organization Deleted'
        USER_BLOCKED = 'user_blocked', 'User Blocked'
        USER_UNBLOCKED = 'user_unblocked', 'User Unblocked'
        PASSWORD_RESET = 'password_reset', 'Password Reset'
        SUBSCRIPTION_RENEWED = 'subscription_renewed', 'Subscription Renewed'
        SUBSCRIPTION_ASSIGNED = 'subscription_assigned', 'Subscription Assigned'
        PAYMENT_RECORDED = 'payment_recorded', 'Payment Recorded'
        ANNOUNCEMENT_SENT = 'announcement_sent', 'Announcement Sent'

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='activity_logs',
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    description = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['action', '-created_at']),
        ]

    def __str__(self):
        return f'{self.get_action_display()} — {self.description}'


def log_activity(action, description, actor=None, request=None):
    ip_address = None
    if request is not None:
        ip_address = request.META.get('REMOTE_ADDR')
    return ActivityLog.objects.create(
        action=action, description=description, actor=actor, ip_address=ip_address,
    )


class PlatformSettings(models.Model):
    site_name = models.CharField(max_length=100, default='QueueLess Nepal')
    support_email = models.EmailField(default='support@queueless.np')
    maintenance_mode = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Platform settings'

    def __str__(self):
        return self.site_name

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
