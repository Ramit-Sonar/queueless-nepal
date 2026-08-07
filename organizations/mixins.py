from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property

from core.mixins import RoleRequiredMixin

from .models import Organization


class OrgAdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = ('org_admin',)
    login_url = 'accounts:business_login'

    @cached_property
    def organization(self):
        return get_object_or_404(Organization, owner=self.request.user)
