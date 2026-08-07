from django import forms
from django.contrib.auth.forms import UserCreationForm
from phonenumber_field.formfields import PhoneNumberField

from accounts.models import User
from queue_management.models import Queue
from services.models import Service
from staff.models import StaffProfile

from .models import Department, Organization


class OrganizationProfileForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = (
            'name', 'category', 'description', 'logo', 'address', 'city',
            'phone_number', 'email', 'opening_time', 'closing_time',
        )
        widgets = {
            'opening_time': forms.TimeInput(attrs={'type': 'time'}),
            'closing_time': forms.TimeInput(attrs={'type': 'time'}),
            'description': forms.Textarea(attrs={'rows': 4}),
        }


class OrganizationSettingsForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = (
            'allow_customer_rebooking', 'max_active_tokens_per_customer',
            'notify_on_new_booking', 'notify_daily_summary',
        )


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ('name', 'description', 'is_active')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ('name', 'department', 'description', 'average_service_minutes', 'daily_token_limit', 'is_active')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization is not None:
            self.fields['department'].queryset = Department.objects.filter(organization=organization)
        self.fields['department'].required = False


class QueueCreateForm(forms.Form):
    service = forms.ModelChoiceField(queryset=Service.objects.none())

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization is not None:
            self.fields['service'].queryset = organization.services.filter(is_active=True)


class QueueEditForm(forms.ModelForm):
    class Meta:
        model = Queue
        fields = ('status', 'priority')


class StaffCreateForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    phone_number = PhoneNumberField(required=False)
    department = forms.ModelChoiceField(queryset=Department.objects.none(), required=False)
    service = forms.ModelChoiceField(
        queryset=Service.objects.none(), required=False,
        help_text='Optional — assign a dedicated counter/service this staff member can book walk-in tokens for.',
    )
    counter_number = forms.CharField(max_length=20, required=False)
    employee_id = forms.CharField(max_length=30, required=False)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'phone_number', 'password1', 'password2')

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._organization = organization
        if organization is not None:
            self.fields['department'].queryset = Department.objects.filter(organization=organization)
            self.fields['service'].queryset = Service.objects.filter(organization=organization, is_active=True)

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.STAFF
        user.email = self.cleaned_data['email']
        user.phone_number = self.cleaned_data.get('phone_number') or None
        if commit:
            user.save()
            StaffProfile.objects.create(
                user=user,
                organization=self._organization,
                department=self.cleaned_data.get('department'),
                service=self.cleaned_data.get('service'),
                counter_number=self.cleaned_data.get('counter_number', ''),
                employee_id=self.cleaned_data.get('employee_id', ''),
            )
        return user


class StaffUserFieldsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'phone_number')

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email


class StaffProfileFieldsForm(forms.ModelForm):
    class Meta:
        model = StaffProfile
        fields = ('department', 'service', 'counter_number', 'employee_id', 'is_active')

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization is not None:
            self.fields['department'].queryset = Department.objects.filter(organization=organization)
            self.fields['service'].queryset = Service.objects.filter(organization=organization, is_active=True)
        self.fields['service'].required = False
