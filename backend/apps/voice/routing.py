from django.urls import path

from apps.voice.consumers import LiveSessionConsumer

websocket_urlpatterns = [
    path("ws/voice/<slug:scenario_slug>/<int:level_order>/", LiveSessionConsumer.as_asgi()),
]
