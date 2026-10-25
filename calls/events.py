from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def publish(call_id, event, data):
    """Push an event to every websocket watching this call."""
    async_to_sync(get_channel_layer().group_send)(
        f"call_{call_id}", {"type": "call.event", "event": event, "data": data}
    )
