from django.views.generic import TemplateView

from accounts.models import User
from organizations.models import Organization
from queue_management.models import Token
from subscriptions.models import SubscriptionPlan


class HomeView(TemplateView):
    template_name = 'core/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['organization_count'] = Organization.objects.filter(
            is_approved=True, is_active=True,
        ).count()
        context['customer_count'] = User.objects.filter(role=User.Role.CUSTOMER).count()
        context['staff_count'] = User.objects.filter(role=User.Role.STAFF, is_active=True).count()
        context['token_count'] = Token.objects.count()
        context['plans'] = SubscriptionPlan.objects.filter(is_active=True)
        return context
