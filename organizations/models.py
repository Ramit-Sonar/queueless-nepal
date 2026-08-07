from django.conf import settings
from django.db import models
from django.utils.text import slugify

from core.models import BaseModel


class Organization(BaseModel):
    class Category(models.TextChoices):
        HOSPITAL = 'hospital', 'Hospital / Clinic'
        BANK = 'bank', 'Bank / Finance'
        GOVERNMENT = 'government', 'Government Office'
        EDUCATION = 'education', 'Education'
        RETAIL = 'retail', 'Retail / Service Center'
        OTHER = 'other', 'Other'

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='organizations',
    )
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to='organization_logos/', null=True, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    opening_time = models.TimeField(null=True, blank=True)
    closing_time = models.TimeField(null=True, blank=True)
    is_approved = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # Queue rules
    allow_customer_rebooking = models.BooleanField(default=True)
    max_active_tokens_per_customer = models.PositiveSmallIntegerField(default=1)

    # Notification settings
    notify_on_new_booking = models.BooleanField(default=True)
    notify_daily_summary = models.BooleanField(default=False)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_approved', 'is_active']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Organization.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                counter += 1
                slug = f'{base_slug}-{counter}'
            self.slug = slug
        super().save(*args, **kwargs)

    def is_open_now(self):
        if not self.opening_time or not self.closing_time:
            return True
        from django.utils import timezone
        now = timezone.localtime().time()
        return self.opening_time <= now <= self.closing_time


class Department(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='departments',
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['organization', 'name'], name='unique_department_per_org'),
        ]

    def __str__(self):
        return f'{self.name} — {self.organization.name}'
