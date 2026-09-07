from django.urls import path

from apps.progress.views import AttemptReportView, JourneyView

urlpatterns = [
    path("journey/", JourneyView.as_view(), name="journey"),
    path("attempts/<int:pk>/", AttemptReportView.as_view(), name="attempt-report"),
]
