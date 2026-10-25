from django.urls import path

from .consumers import CallConsumer

websocket_urlpatterns = [path("ws/calls/<str:call_id>/", CallConsumer.as_asgi())]
