from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from calls.urls import api_urlpatterns, bridge_urlpatterns

urlpatterns = [
    path("admin/", admin.site.urls),
    # Auth
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Core: registration, profile, password change
    path("api/", include("core.urls")),
    # Calls API
    path("api/", include(api_urlpatterns)),
    # Bridge (Go ↔ Django, shared-secret auth)
    path("bridge/", include(bridge_urlpatterns)),
]
