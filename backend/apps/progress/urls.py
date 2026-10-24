from django.urls import path

from apps.progress.views import AttemptMistakeAudioView, AttemptReportView, JourneyView

urlpatterns = [
    path("journey/", JourneyView.as_view(), name="journey"),
    path("attempts/<int:pk>/", AttemptReportView.as_view(), name="attempt-report"),
    path(
        "attempts/<int:pk>/mistakes/<int:occurrence_id>/audio/",
        AttemptMistakeAudioView.as_view(),
        name="attempt-mistake-audio",
    ),
]
