from django.urls import path

from apps.agents.views import ScenarioBriefingView

urlpatterns = [
    path(
        "scenarios/<slug:scenario_slug>/levels/<int:level_order>/briefing/",
        ScenarioBriefingView.as_view(),
        name="scenario-briefing",
    ),
]
