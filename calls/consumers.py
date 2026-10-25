import uuid
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework.authtoken.models import Token

from .models import Call


@database_sync_to_async
def _user_for(key):
    try:
        return Token.objects.select_related("user").get(key=key).user
    except Token.DoesNotExist:
        return AnonymousUser()


class TokenAuthMiddleware(BaseMiddleware):
    """Accepts `Authorization: Token <key>` or `?token=<key>` on the handshake."""

    async def __call__(self, scope, receive, send):
        key = None
        auth = dict(scope["headers"]).get(b"authorization", b"").decode()
        if auth.startswith("Token "):
            key = auth[6:]
        else:
            key = parse_qs(scope["query_string"].decode()).get("token", [None])[0]
        scope["user"] = await _user_for(key) if key else AnonymousUser()
        return await super().__call__(scope, receive, send)


@database_sync_to_async
def _owns(user, call_id):
    try:
        return Call.objects.filter(pk=uuid.UUID(call_id), owner=user).exists()
    except ValueError:
        return False


class CallConsumer(AsyncJsonWebsocketConsumer):
    """Read-only live feed for one call. Sends {"event": ..., "data": ...}."""

    async def connect(self):
        call_id = self.scope["url_route"]["kwargs"]["call_id"]
        user = self.scope["user"]
        if not user.is_authenticated or not await _owns(user, call_id):
            await self.close(code=4403)
            return
        self.group = f"call_{uuid.UUID(call_id)}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def call_event(self, message):
        await self.send_json({"event": message["event"], "data": message["data"]})
