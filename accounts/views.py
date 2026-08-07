from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView as BaseLoginView,
    LogoutView as BaseLogoutView,
    PasswordChangeDoneView as BasePasswordChangeDoneView,
    PasswordChangeView as BasePasswordChangeView,
    PasswordResetCompleteView as BasePasswordResetCompleteView,
    PasswordResetConfirmView as BasePasswordResetConfirmView,
    PasswordResetDoneView as BasePasswordResetDoneView,
    PasswordResetView as BasePasswordResetView,
)
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import CreateView, DetailView, UpdateView

from .forms import CustomerRegisterForm, ProfileUpdateForm
from .models import User


class RegisterView(CreateView):
    model = User
    form_class = CustomerRegisterForm
    template_name = 'accounts/register.html'

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        messages.success(self.request, f'Welcome to QueueLess Nepal, {self.object.first_name}!')
        return response

    def get_success_url(self):
        next_url = self.request.POST.get('next') or self.request.GET.get('next')
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={self.request.get_host()}, require_https=self.request.is_secure(),
        ):
            return next_url
        return reverse_lazy('accounts:post_login_redirect')


class RoleLoginView(BaseLoginView):
    allowed_roles = ()
    wrong_role_message = "Please use the correct sign-in page for your account."

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.user.role not in self.allowed_roles:
            logout(self.request)
            messages.error(self.request, self.wrong_role_message)
            return self.form_invalid(form)
        return response


class LoginView(RoleLoginView):
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True
    allowed_roles = (User.Role.CUSTOMER,)
    wrong_role_message = (
        "This sign-in is for customer accounts. Organization or staff members should use the "
        "Organization / Staff login."
    )


class BusinessLoginView(RoleLoginView):
    template_name = 'accounts/business_login.html'
    redirect_authenticated_user = True
    allowed_roles = (User.Role.ORG_ADMIN, User.Role.STAFF)
    wrong_role_message = (
        "This sign-in is for organization and staff accounts. Customers should use the customer login."
    )


class SuperAdminLoginView(RoleLoginView):
    template_name = 'accounts/super_admin_login.html'
    redirect_authenticated_user = True
    allowed_roles = (User.Role.SUPER_ADMIN,)
    wrong_role_message = "This sign-in is reserved for super admin accounts."


class LogoutView(BaseLogoutView):
    next_page = reverse_lazy('accounts:login')


class ProfileView(LoginRequiredMixin, DetailView):
    model = User
    template_name = 'accounts/profile.html'
    context_object_name = 'profile_user'

    def get_object(self, queryset=None):
        return self.request.user


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = ProfileUpdateForm
    template_name = 'accounts/profile_edit.html'
    success_url = reverse_lazy('accounts:profile')

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, 'Your profile has been updated.')
        return super().form_valid(form)


class PasswordChangeView(LoginRequiredMixin, BasePasswordChangeView):
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('accounts:password_change_done')


class PasswordChangeDoneView(LoginRequiredMixin, BasePasswordChangeDoneView):
    template_name = 'accounts/password_change_done.html'


class PasswordResetView(BasePasswordResetView):
    template_name = 'accounts/password_reset.html'
    email_template_name = 'accounts/password_reset_email.html'
    subject_template_name = 'accounts/password_reset_subject.txt'
    success_url = reverse_lazy('accounts:password_reset_done')


class PasswordResetDoneView(BasePasswordResetDoneView):
    template_name = 'accounts/password_reset_done.html'


class PasswordResetConfirmView(BasePasswordResetConfirmView):
    template_name = 'accounts/password_reset_confirm.html'
    success_url = reverse_lazy('accounts:password_reset_complete')


class PasswordResetCompleteView(BasePasswordResetCompleteView):
    template_name = 'accounts/password_reset_complete.html'


def post_login_redirect(request):
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    if request.user.role == User.Role.CUSTOMER:
        return redirect('customers:home')

    if request.user.role == User.Role.ORG_ADMIN:
        return redirect('organizations:dashboard')

    if request.user.role == User.Role.STAFF:
        return redirect('staff:dashboard')

    if request.user.role == User.Role.SUPER_ADMIN:
        return redirect('dashboard:platform_dashboard')

    messages.info(request, "Your role's dashboard is coming in a future update.")
    return redirect('core:home')
