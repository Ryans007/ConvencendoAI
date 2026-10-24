from django.urls import path

from apps.users.views import (
    ChangePasswordView,
    CurrentUserView,
    LoginView,
    LogoutView,
    TokenRefreshView,
)

urlpatterns = [
    path("auth/token/", LoginView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/me/", CurrentUserView.as_view(), name="current_user"),
    path("auth/password/", ChangePasswordView.as_view(), name="change_password"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
]
