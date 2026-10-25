from django.urls import path
from rest_framework.routers import DefaultRouter

from . import bridge_views, views

router = DefaultRouter()
router.register("calls", views.CallViewSet, basename="call")
router.register("allowlist", views.AllowedNumberViewSet, basename="allowlist")

api_urlpatterns = [
    path("settings/", views.SettingsView.as_view()),
    path("devices/", views.DeviceView.as_view()),
    *router.urls,
]

bridge_urlpatterns = [
    path("calls/", bridge_views.BridgeCallStart.as_view()),
    path("calls/<uuid:call_id>/segments/", bridge_views.BridgeSegments.as_view()),
    path("calls/<uuid:call_id>/notes/", bridge_views.BridgeNote.as_view()),
    path("calls/<uuid:call_id>/end/", bridge_views.BridgeCallEnd.as_view()),
]
