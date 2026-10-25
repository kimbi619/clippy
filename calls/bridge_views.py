"""Endpoints for the Go bridge (shared-secret header, no user auth)."""
import hmac

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from . import events
from .models import AllowedNumber, Call, Participant, TranscriptSegment, UserSettings
from .serializers import NoteSerializer, SegmentSerializer

_BRIDGE_TAG = ["bridge (internal)"]


class HasBridgeKey(BasePermission):
    def has_permission(self, request, view):
        key = request.headers.get("X-Bridge-Key", "")
        return hmac.compare_digest(key.encode(), settings.BRIDGE_API_KEY.encode())


class BridgeView(APIView):
    authentication_classes = []
    permission_classes = [HasBridgeKey]


class BridgeCallStart(BridgeView):
    @extend_schema(
        summary="Start call (bot added to a call)",
        request=inline_serializer(
            "BridgeCallStartRequest",
            fields={
                "added_by": serializers.CharField(),
                "platform": serializers.CharField(default="whatsapp"),
                "external_id": serializers.CharField(required=False),
            },
        ),
        responses={
            201: inline_serializer("BridgeCallStartResponse", fields={"id": serializers.UUIDField(), "trigger_name": serializers.CharField()}),
            200: inline_serializer("BridgeCallStartResponseExisting", fields={"id": serializers.UUIDField(), "trigger_name": serializers.CharField()}),
            403: OpenApiResponse(description="Caller not on allowlist — bridge must leave the call."),
        },
        tags=_BRIDGE_TAG,
    )
    def post(self, request):
        added_by = str(request.data.get("added_by", ""))
        platform = request.data.get("platform", "whatsapp")
        external_id = str(request.data.get("external_id", ""))

        allowed = AllowedNumber.objects.select_related("owner").filter(number=added_by).first()
        if allowed is None:
            return Response({"detail": "number not allowed"}, status=status.HTTP_403_FORBIDDEN)

        if external_id:  # retry-safe
            existing = Call.objects.filter(
                owner=allowed.owner, platform=platform, external_id=external_id, status=Call.Status.ACTIVE
            ).first()
            if existing:
                call, created = existing, False
            else:
                call, created = Call.objects.create(
                    owner=allowed.owner, platform=platform, external_id=external_id, added_by=added_by
                ), True
        else:
            call, created = Call.objects.create(owner=allowed.owner, platform=platform, added_by=added_by), True

        trigger = UserSettings.objects.get_or_create(user=allowed.owner)[0].trigger_name
        return Response(
            {"id": str(call.id), "trigger_name": trigger},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class BridgeSegments(BridgeView):
    @extend_schema(
        summary="Post transcript segments",
        request=SegmentSerializer(many=True),
        responses={200: inline_serializer("BridgeSegmentsResponse", fields={"count": serializers.IntegerField()})},
        tags=_BRIDGE_TAG,
    )
    def post(self, request, call_id):
        call = get_object_or_404(Call, pk=call_id)
        ser = SegmentSerializer(data=request.data, many=True)
        ser.is_valid(raise_exception=True)
        out = []
        with transaction.atomic():
            for item in ser.validated_data:
                seq = item.pop("seq")
                seg, _ = TranscriptSegment.objects.update_or_create(call=call, seq=seq, defaults=item)
                if seg.speaker:
                    Participant.objects.get_or_create(call=call, label=seg.speaker)
                out.append(SegmentSerializer(seg).data)
        if out:
            events.publish(call.id, "segments", out)
        return Response({"count": len(out)})


class BridgeNote(BridgeView):
    @extend_schema(
        summary="Post a note from the bot",
        request=NoteSerializer,
        responses={201: NoteSerializer},
        tags=_BRIDGE_TAG,
    )
    def post(self, request, call_id):
        call = get_object_or_404(Call, pk=call_id)
        ser = NoteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = NoteSerializer(ser.save(call=call)).data
        events.publish(call.id, "note", data)
        return Response(data, status=status.HTTP_201_CREATED)


class BridgeCallEnd(BridgeView):
    @extend_schema(
        summary="End call",
        request=inline_serializer("BridgeCallEndRequest", fields={"summary": serializers.CharField(required=False)}),
        responses={204: OpenApiResponse(description="Call ended.")},
        tags=_BRIDGE_TAG,
    )
    def post(self, request, call_id):
        call = get_object_or_404(Call, pk=call_id)
        if call.status != Call.Status.ENDED:
            call.status = Call.Status.ENDED
            call.ended_at = timezone.now()
        if "summary" in request.data:
            call.summary = str(request.data["summary"])
        call.save()
        events.publish(call.id, "call_ended", {"ended_at": call.ended_at.isoformat(), "summary": call.summary})
        return Response(status=status.HTTP_204_NO_CONTENT)
