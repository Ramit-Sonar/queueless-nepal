from django.contrib import admin

from .models import ActivityLog, PlatformSettings


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'description', 'actor', 'created_at')
    list_filter = ('action',)
    search_fields = ('description', 'actor__username')


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    list_display = ('site_name', 'support_email', 'maintenance_mode', 'updated_at')
