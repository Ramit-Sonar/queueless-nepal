from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property

from core.mixins import RoleRequiredMixin

from .models import StaffProfile


class StaffRequiredMixin(RoleRequiredMixin):
    allowed_roles = ('staff',)
    login_url = 'accounts:business_login'

    @cached_property
    def staff_profile(self):
        return get_object_or_404(StaffProfile, user=self.request.user, is_active=True)

    @cached_property
    def organization(self):
        return self.staff_profile.organization
