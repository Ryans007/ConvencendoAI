from django.contrib import admin

from apps.users.admin.login_failure import LoginFailureAdmin
from apps.users.admin.login_form import LockoutAdminAuthenticationForm
from apps.users.admin.user import UserAdmin

admin.site.login_form = LockoutAdminAuthenticationForm

__all__ = ["LockoutAdminAuthenticationForm", "LoginFailureAdmin", "UserAdmin"]
