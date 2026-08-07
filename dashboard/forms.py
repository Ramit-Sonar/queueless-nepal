from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from phonenumber_field.formfields import PhoneNumberField

from accounts.models import User
from core.models import PlatformSettings
from organizations.models import Organization
from payments.models import Payment
from subscriptions.models import SubscriptionPlan


class OrganizationCreateForm(UserCreationForm):
    """Creates the owning org_admin account and the organization together."""

    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    phone_number = PhoneNumberField(required=False)

    org_name = forms.CharField(max_length=150, label='Organization name')
    org_category = forms.ChoiceField(choices=Organization.Category.choices, label='Category')
    org_city = forms.CharField(max_length=100, required=False, label='City')

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'phone_number', 'password1', 'password2')

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    @transaction.atomic
    def save(self, commit=True):
        owner = super().save(commit=False)
        owner.role = User.Role.ORG_ADMIN
        owner.email = self.cleaned_data['email']
        owner.phone_number = self.cleaned_data.get('phone_number') or None
        if commit:
            owner.save()
            Organization.objects.create(
                owner=owner,
                name=self.cleaned_data['org_name'],
                category=self.cleaned_data['org_category'],
                city=self.cleaned_data.get('org_city', ''),
                is_approved=False,
                is_active=True,
            )
        return owner


class PlanEditForm(forms.ModelForm):
    class Meta:
        model = SubscriptionPlan
        fields = ('monthly_price', 'max_staff', 'max_services', 'max_departments', 'is_active')


class SubscriptionAssignForm(forms.Form):
    plan = forms.ModelChoiceField(queryset=SubscriptionPlan.objects.filter(is_active=True))


class PaymentForm(forms.Form):
    organization = forms.ModelChoiceField(queryset=Organization.objects.filter(subscription__isnull=False))
    amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)
    provider = forms.ChoiceField(choices=Payment.Provider.choices)
    notes = forms.CharField(max_length=255, required=False)


class AnnouncementForm(forms.Form):
    AUDIENCE_CHOICES = [
        ('all', 'Everyone'),
        ('customer', 'Customers'),
        ('org_admin', 'Organization Admins'),
        ('staff', 'Staff'),
    ]
    audience = forms.ChoiceField(choices=AUDIENCE_CHOICES)
    title = forms.CharField(max_length=150)
    message = forms.CharField(max_length=255, widget=forms.Textarea(attrs={'rows': 3}))


class PlatformSettingsForm(forms.ModelForm):
    class Meta:
        model = PlatformSettings
        fields = ('site_name', 'support_email', 'maintenance_mode')
