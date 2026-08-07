import uuid

from django import forms
from phonenumber_field.formfields import PhoneNumberField

from accounts.models import User
from queue_management.models import Token
from services.models import Service


class TransferForm(forms.Form):
    service = forms.ModelChoiceField(queryset=Service.objects.none(), label='Forward to service')
    reason = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={'placeholder': 'Optional reason'}))
    priority = forms.ChoiceField(choices=Token.Priority.choices, required=False, initial=Token.Priority.NORMAL)

    def __init__(self, *args, organization=None, exclude_service=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Service.objects.none()
        if organization is not None:
            queryset = organization.services.filter(is_active=True)
            if exclude_service is not None:
                queryset = queryset.exclude(pk=exclude_service.pk)
        self.fields['service'].queryset = queryset


class WalkInBookingForm(forms.Form):
    """Lets a staff member book a token on behalf of a walk-in customer who
    has no phone/app. If an account with the given phone number already
    exists, its owner is booked; otherwise a lightweight customer account
    is created on the fly from the first/last name."""

    service = forms.ModelChoiceField(queryset=Service.objects.none(), required=True)
    phone_number = PhoneNumberField(required=True, label='Customer phone number')
    first_name = forms.CharField(max_length=150, required=False, label="Customer's first name")
    last_name = forms.CharField(max_length=150, required=False, label="Customer's last name")

    def __init__(self, *args, service_queryset, locked_service=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._locked_service = locked_service
        if locked_service is not None:
            self.fields['service'].queryset = Service.objects.filter(pk=locked_service.pk)
            self.fields['service'].initial = locked_service
            self.fields['service'].widget = forms.HiddenInput()
        else:
            self.fields['service'].queryset = service_queryset

    def clean(self):
        cleaned_data = super().clean()
        if self._locked_service is not None:
            cleaned_data['service'] = self._locked_service

        phone_number = cleaned_data.get('phone_number')
        if not phone_number:
            return cleaned_data

        existing = User.objects.filter(phone_number=phone_number).first()
        if existing is not None and existing.role != User.Role.CUSTOMER:
            self.add_error(
                'phone_number',
                'This phone number is already linked to a different type of account.',
            )
            return cleaned_data

        if existing is None and not cleaned_data.get('first_name'):
            self.add_error('first_name', "Required for a new customer — we couldn't find an existing account with this phone number.")

        cleaned_data['existing_customer'] = existing
        return cleaned_data

    def get_or_create_customer(self):
        existing = self.cleaned_data.get('existing_customer')
        if existing is not None:
            return existing, False

        phone_number = self.cleaned_data['phone_number']
        username_base = f"walkin{''.join(filter(str.isdigit, str(phone_number)))[-10:]}"
        username = username_base
        while User.objects.filter(username=username).exists():
            username = f'{username_base}{uuid.uuid4().hex[:4]}'

        customer = User(
            username=username,
            first_name=self.cleaned_data.get('first_name', ''),
            last_name=self.cleaned_data.get('last_name', ''),
            email=f'walkin.{uuid.uuid4().hex[:12]}@queueless.local',
            phone_number=phone_number,
            role=User.Role.CUSTOMER,
        )
        customer.set_unusable_password()
        customer.save()
        return customer, True
