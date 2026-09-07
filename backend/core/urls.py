from django.contrib import admin
from django.urls import include, path

from core.views import HealthView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", HealthView.as_view(), name="health"),
    path("api/", include("apps.users.urls")),
    path("api/", include("apps.progress.urls")),
    path("api/", include("apps.agents.urls")),
]
