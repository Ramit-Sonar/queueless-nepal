from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from decouple import config

from core.models import ActivityLog, log_activity


User = get_user_model()


def create_default_role_user(username_env, password_env, email_env, role, **extra_fields):
    username = config(username_env, default=None)
    password = config(password_env, default=None)
    email = config(email_env, default=None)

    if not username or not password:
        return

    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            'email': email or '',
            'role': role,
            **extra_fields,
        },
    )

    modified = False

    if user.role != role:
        user.role = role
        modified = True

    if email and user.email != email:
        user.email = email
        modified = True

    for field, value in extra_fields.items():
        if getattr(user, field) != value:
            setattr(user, field, value)
            modified = True

    if created or not user.check_password(password):
        user.set_password(password)
        modified = True

    if modified:
        user.save()


@receiver(post_migrate)
def create_default_role_users(sender, **kwargs):
    if sender.name != 'accounts':
        return

    create_default_role_user(
        'CUSTOMER_USERNAME',
        'CUSTOMER_PASSWORD',
        'CUSTOMER_EMAIL',
        User.Role.CUSTOMER,
        is_staff=False,
        is_superuser=False,
        is_active=True,
    )
    create_default_role_user(
        'ORG_ADMIN_USERNAME',
        'ORG_ADMIN_PASSWORD',
        'ORG_ADMIN_EMAIL',
        User.Role.ORG_ADMIN,
        is_staff=True,
        is_superuser=False,
        is_active=True,
    )
    create_default_role_user(
        'STAFF_USERNAME',
        'STAFF_PASSWORD',
        'STAFF_EMAIL',
        User.Role.STAFF,
        is_staff=True,
        is_superuser=False,
        is_active=True,
    )
    create_default_role_user(
        'SUPER_ADMIN_USERNAME',
        'SUPER_ADMIN_PASSWORD',
        'SUPER_ADMIN_EMAIL',
        User.Role.SUPER_ADMIN,
        is_staff=True,
        is_superuser=True,
        is_active=True,
    )


@receiver(user_logged_in)
def record_login(sender, request, user, **kwargs):
    log_activity(ActivityLog.Action.LOGIN, str(user), actor=user, request=request)
