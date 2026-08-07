from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'subscription', 'amount', 'provider', 'status', 'paid_at')
    list_filter = ('status', 'provider')
    search_fields = ('transaction_id', 'subscription__organization__name')
