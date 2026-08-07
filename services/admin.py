from django.contrib import admin

from .models import Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'department', 'average_service_minutes', 'is_active')
    list_filter = ('is_active', 'organization')
    search_fields = ('name', 'organization__name')
