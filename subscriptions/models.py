from django.db import models
from django.utils import timezone

from core.models import BaseModel
from organizations.models import Organization


class SubscriptionPlan(BaseModel):
    class Tier(models.TextChoices):
        STARTER = 'starter', 'Starter'
        PROFESSIONAL = 'professional', 'Professional'
        ENTERPRISE = 'enterprise', 'Enterprise'

    tier = models.CharField(max_length=20, choices=Tier.choices, unique=True)
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2)
    max_staff = models.PositiveIntegerField()
    max_services = models.PositiveIntegerField()
    max_departments = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['monthly_price']

    def __str__(self):
        return self.get_tier_display()


class Subscription(BaseModel):
    class Status(models.TextChoices):
        TRIALING = 'trialing', 'Trialing'
        ACTIVE = 'active', 'Active'
        EXPIRED = 'expired', 'Expired'
        CANCELLED = 'cancelled', 'Cancelled'

    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name='subscription',
    )
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='subscriptions')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TRIALING)
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField()

    class Meta:
        ordering = ['end_date']

    def __str__(self):
        return f'{self.organization.name} — {self.plan.get_tier_display()}'

    @property
    def is_expired(self):
        return self.end_date < timezone.localdate()

    @property
    def days_until_expiry(self):
        return (self.end_date - timezone.localdate()).days

    @property
    def is_expiring_soon(self):
        return self.status == self.Status.ACTIVE and 0 <= self.days_until_expiry <= 7

    def renew(self, days=30):
        base = self.end_date if self.end_date > timezone.localdate() else timezone.localdate()
        self.end_date = base + timezone.timedelta(days=days)
        self.status = self.Status.ACTIVE
        self.save(update_fields=['end_date', 'status'])
