from django.contrib import admin

from .models import CustomerProfile


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'notify_by_email', 'notify_by_sms', 'preferred_language')
    search_fields = ('user__username', 'user__email')
