from django.db.models.signals import post_save
from django.dispatch import receiver

from queue_management.models import Token

from .models import Notification

STATUS_NOTIFICATIONS = {
    Token.Status.CALLED: (
        Notification.NotificationType.TOKEN_CALLED,
        'Your token has been called',
        'Token {number} is being called at {service}. Please proceed to the counter.',
    ),
    Token.Status.COMPLETED: (
        Notification.NotificationType.TOKEN_COMPLETED,
        'Service completed',
        'Your service for token {number} at {service} has been completed. Thank you!',
    ),
}


@receiver(post_save, sender=Token)
def notify_on_token_status_change(sender, instance, created, **kwargs):
    if created:
        return
    entry = STATUS_NOTIFICATIONS.get(instance.status)
    if not entry:
        return
    notification_type, title, message_template = entry
    Notification.objects.create(
        user=instance.customer,
        notification_type=notification_type,
        title=title,
        message=message_template.format(number=instance.display_number, service=instance.queue.service.name),
        related_token=instance,
    )
