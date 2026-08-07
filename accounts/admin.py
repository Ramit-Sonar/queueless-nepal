from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ('username', 'email', 'role', 'is_verified', 'is_active', 'date_joined')
    list_filter = ('role', 'is_verified', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'phone_number')
    ordering = ('-date_joined',)
    fieldsets = UserAdmin.fieldsets + (
        ('QueueLess Profile', {
            'fields': ('role', 'phone_number', 'profile_picture', 'is_verified'),
        }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('QueueLess Profile', {
            'fields': ('email', 'role', 'phone_number'),
        }),
    )
