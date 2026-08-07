from django.contrib import admin

from .models import Queue, Token


class TokenInline(admin.TabularInline):
    model = Token
    extra = 0
    fields = ('token_number', 'customer', 'status', 'called_at', 'completed_at')
    readonly_fields = ('token_number',)


@admin.register(Queue)
class QueueAdmin(admin.ModelAdmin):
    list_display = ('service', 'queue_date', 'status', 'last_token_number')
    list_filter = ('status', 'queue_date', 'service__organization')
    search_fields = ('service__name',)
    inlines = [TokenInline]


@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    list_display = ('display_number', 'queue', 'customer', 'status', 'created_at')
    list_filter = ('status', 'queue__service__organization')
    search_fields = ('customer__username', 'customer__email', 'token_number')
    readonly_fields = ('token_number',)
