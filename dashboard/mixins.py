from core.mixins import RoleRequiredMixin


class SuperAdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = ('super_admin',)
    login_url = 'accounts:super_admin_login'
