from django.db import models

from core.models import BaseModel
from organizations.models import Department, Organization


class Service(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='services',
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        related_name='services',
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    average_service_minutes = models.PositiveIntegerField(
        default=10,
        help_text='Average time to serve one customer, used to estimate wait time.',
    )
    daily_token_limit = models.PositiveIntegerField(
        default=100,
        help_text='Maximum tokens accepted per day for this service.',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['organization', 'name'], name='unique_service_per_org'),
        ]
        indexes = [
            models.Index(fields=['organization', 'is_active']),
        ]

    def __str__(self):
        return f'{self.name} — {self.organization.name}'
