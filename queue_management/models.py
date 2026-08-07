from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from core.models import BaseModel
from services.models import Service


class Queue(BaseModel):
    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        CLOSED = 'closed', 'Closed'

    class Priority(models.TextChoices):
        NORMAL = 'normal', 'Normal'
        HIGH = 'high', 'High'
        URGENT = 'urgent', 'Urgent'

    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='queues')
    queue_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    last_token_number = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-queue_date']
        constraints = [
            models.UniqueConstraint(fields=['service', 'queue_date'], name='unique_queue_per_service_per_day'),
        ]
        indexes = [
            models.Index(fields=['service', 'queue_date']),
        ]

    def __str__(self):
        return f'{self.service.name} — {self.queue_date}'

    @classmethod
    def get_or_create_today(cls, service):
        queue, _ = cls.objects.get_or_create(
            service=service,
            queue_date=timezone.localdate(),
        )
        return queue

    @transaction.atomic
    def issue_token(self, customer):
        locked_queue = Queue.objects.select_for_update().get(pk=self.pk)
        locked_queue.last_token_number += 1
        locked_queue.save(update_fields=['last_token_number'])
        return Token.objects.create(
            queue=locked_queue,
            customer=customer,
            token_number=locked_queue.last_token_number,
        )

    @property
    def currently_serving(self):
        return self.tokens.filter(
            status__in=[Token.Status.CALLED, Token.Status.SERVING],
        ).order_by('-called_at').first()

    @property
    def waiting_tokens(self):
        return self.tokens.filter(status=Token.Status.WAITING).order_by(
            models.Case(
                models.When(priority=Token.Priority.URGENT, then=0),
                models.When(priority=Token.Priority.HIGH, then=1),
                default=2,
                output_field=models.IntegerField(),
            ),
            'token_number',
        )

    @property
    def skipped_tokens(self):
        return self.tokens.filter(status=Token.Status.SKIPPED).order_by('token_number')

    @property
    def completed_tokens_today(self):
        return self.tokens.filter(status=Token.Status.COMPLETED).order_by('-completed_at')


class Token(BaseModel):
    class Status(models.TextChoices):
        WAITING = 'waiting', 'Waiting'
        CALLED = 'called', 'Called'
        SERVING = 'serving', 'Serving'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'
        SKIPPED = 'skipped', 'Skipped'
        NO_SHOW = 'no_show', 'No Show'

    class Priority(models.TextChoices):
        NORMAL = 'normal', 'Normal'
        HIGH = 'high', 'High'
        URGENT = 'urgent', 'Urgent'

    ACTIVE_STATUSES = [Status.WAITING, Status.CALLED, Status.SERVING]

    queue = models.ForeignKey(Queue, on_delete=models.CASCADE, related_name='tokens')
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tokens',
    )
    served_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='served_tokens',
        null=True,
        blank=True,
    )
    transferred_from = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        related_name='transferred_to_tokens',
        null=True,
        blank=True,
    )
    token_number = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WAITING)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    called_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['token_number']
        constraints = [
            models.UniqueConstraint(fields=['queue', 'token_number'], name='unique_token_number_per_queue'),
        ]
        indexes = [
            models.Index(fields=['queue', 'status']),
            models.Index(fields=['customer', 'status']),
        ]

    def __str__(self):
        return f'#{self.token_number} — {self.queue.service.name}'

    @property
    def display_number(self):
        prefix = self.queue.service.name[:2].upper()
        return f'{prefix}-{self.token_number:03d}'

    @property
    def position_in_queue(self):
        if self.status not in self.ACTIVE_STATUSES:
            return 0
        return self.queue.tokens.filter(
            status__in=self.ACTIVE_STATUSES,
            token_number__lt=self.token_number,
        ).count()

    @property
    def estimated_wait_minutes(self):
        return self.position_in_queue * self.queue.service.average_service_minutes

    @property
    def service_journey(self):
        """Full chain of forward-linked tokens for this customer's visit, oldest first."""
        chain = []
        node = self
        while node.transferred_from_id:
            node = node.transferred_from
            chain.insert(0, node)
        chain.append(self)
        node = self
        while True:
            next_node = node.transferred_to_tokens.select_related('queue__service').first()
            if not next_node:
                break
            chain.append(next_node)
            node = next_node
        return chain

    def cancel(self):
        self.status = self.Status.CANCELLED
        self.cancelled_at = timezone.now()
        self.save(update_fields=['status', 'cancelled_at'])

    def mark_called(self):
        self.status = self.Status.CALLED
        self.called_at = timezone.now()
        self.save(update_fields=['status', 'called_at'])

    def mark_serving(self, staff=None):
        self.status = self.Status.SERVING
        self.started_at = timezone.now()
        update_fields = ['status', 'started_at']
        if staff is not None:
            self.served_by = staff
            update_fields.append('served_by')
        self.save(update_fields=update_fields)

    def mark_completed(self, staff=None):
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        update_fields = ['status', 'completed_at']
        if staff is not None:
            self.served_by = staff
            update_fields.append('served_by')
        self.save(update_fields=update_fields)

    def mark_skipped(self):
        self.status = self.Status.SKIPPED
        self.save(update_fields=['status'])
