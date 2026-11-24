
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):

    list_display = (
        'username',
        'first_name',
        'last_name',
        'phone_number',
        'email',
        'is_active',
        'date_joined',
    )

    list_filter = (
        'is_active',
        'is_staff',
        'is_superuser',
        'date_joined',
    )

    search_fields = (
        'username',
        'first_name',
        'last_name',
        'phone_number',
        'email',
    )

    ordering = ('-date_joined',)

    fieldsets = UserAdmin.fieldsets + (
        ('Additional Information', {
            'fields': (
                'phone_number',
                'profile_picture',
                'created_at',
                'updated_at',
            )
        }),
    )

    readonly_fields = (
        'created_at',
        'updated_at',
        'last_login',
        'date_joined',
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Additional Information', {
            'fields': (
                'first_name',
                'last_name',
                'phone_number',
                'email',
            )
        }),
    )
