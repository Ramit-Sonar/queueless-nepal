from django.contrib import admin

from .models import StaffProfile


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'department', 'counter_number', 'is_active')
    list_filter = ('is_active', 'organization', 'department')
    search_fields = ('user__username', 'user__email', 'employee_id')
