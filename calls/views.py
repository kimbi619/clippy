from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from . import events
from .models import AllowedNumber, Call, Device, Note, Participant, UserSettings
from .serializers import (
    AllowedNumberSerializer,
    CallDetailSerializer,
    CallListSerializer,
    DeviceSerializer,
    NoteSerializer,
    ParticipantSerializer,
    SegmentSerializer,
    UserSettingsSerializer,
)


@extend_schema_view(
    list=extend_schema(summary="List calls", tags=["calls"]),
    retrieve=extend_schema(summary="Get call detail", tags=["calls"]),
    destroy=extend_schema(summary="Delete call", tags=["calls"]),
)
class CallViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    lookup_value_regex = r"[0-9a-f-]{36}"

    def get_queryset(self):
        return Call.objects.filter(owner=self.request.user)

    def get_serializer_class(self):
        return CallDetailSerializer if self.action == "retrieve" else CallListSerializer

    @extend_schema(
        summary="Get transcript segments",
        parameters=[OpenApiParameter("after", int, description="Return only segments with seq > after")],
        responses={200: SegmentSerializer(many=True)},
        tags=["calls"],
    )
    @action(detail=True, methods=["get"])
    def segments(self, request, pk=None):
        qs = self.get_object().segments.all()
        after = request.query_params.get("after")
        if after is not None and after.isdigit():
            qs = qs.filter(seq__gt=int(after))
        return Response(SegmentSerializer(qs, many=True).data)

    @extend_schema(
        methods=["get"],
        summary="List notes",
        responses={200: NoteSerializer(many=True)},
        tags=["calls"],
    )
    @extend_schema(
        methods=["post"],
        summary="Add a note",
        request=NoteSerializer,
        responses={201: NoteSerializer},
        tags=["calls"],
    )
    @action(detail=True, methods=["get", "post"])
    def notes(self, request, pk=None):
        call = self.get_object()
        if request.method == "GET":
            return Response(NoteSerializer(call.notes.all(), many=True).data)
        ser = NoteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        note = ser.save(call=call)
        data = NoteSerializer(note).data
        events.publish(call.id, "note", data)
        return Response(data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Name a speaker label",
        request=ParticipantSerializer,
        responses={200: ParticipantSerializer},
        tags=["calls"],
    )
    @action(detail=True, methods=["patch"], url_path=r"participants/(?P<label>[^/]+)")
    def participant(self, request, pk=None, label=None):
        part = Participant.objects.filter(call=self.get_object(), label=label).first()
        if part is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        ser = ParticipantSerializer(part, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class SettingsView(RetrieveUpdateAPIView):
    serializer_class = UserSettingsSerializer

    def get_object(self):
        return UserSettings.objects.get_or_create(user=self.request.user)[0]


@extend_schema_view(
    list=extend_schema(summary="List allowed numbers", tags=["allowlist"]),
    retrieve=extend_schema(summary="Get allowed number", tags=["allowlist"]),
    create=extend_schema(summary="Add allowed number", tags=["allowlist"]),
    update=extend_schema(summary="Update allowed number", tags=["allowlist"]),
    partial_update=extend_schema(summary="Patch allowed number", tags=["allowlist"]),
    destroy=extend_schema(summary="Remove allowed number", tags=["allowlist"]),
)
class AllowedNumberViewSet(viewsets.ModelViewSet):
    serializer_class = AllowedNumberSerializer
    lookup_value_regex = r"[0-9]+"

    def get_queryset(self):
        return AllowedNumber.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class DeviceView(APIView):
    @extend_schema(
        request=DeviceSerializer,
        responses={204: OpenApiResponse(description="Token registered.")},
        summary="Register FCM push token",
        tags=["devices"],
    )
    def post(self, request):
        ser = DeviceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        Device.objects.update_or_create(
            token=ser.validated_data["token"],
            defaults={"user": request.user, "platform": ser.validated_data["platform"]},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
