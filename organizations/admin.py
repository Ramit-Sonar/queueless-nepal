from django.contrib import admin

from .models import Department, Organization


class DepartmentInline(admin.TabularInline):
    model = Department
    extra = 0


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'city', 'is_approved', 'is_active', 'created_at')
    list_filter = ('category', 'is_approved', 'is_active', 'city')
    search_fields = ('name', 'email', 'phone_number', 'city')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [DepartmentInline]


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'is_active')
    list_filter = ('is_active', 'organization')
    search_fields = ('name', 'organization__name')
