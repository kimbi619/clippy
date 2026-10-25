import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "clippy.settings")

django_asgi_app = get_asgi_application()

from calls.consumers import TokenAuthMiddleware  # noqa: E402 — must import after Django setup
from calls.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": TokenAuthMiddleware(URLRouter(websocket_urlpatterns)),
})
