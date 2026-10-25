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


class CallViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    def get_queryset(self):
        return Call.objects.filter(owner=self.request.user)

    def get_serializer_class(self):
        return CallDetailSerializer if self.action == "retrieve" else CallListSerializer

    @action(detail=True, methods=["get"])
    def segments(self, request, pk=None):
        """Transcript. ?after=<seq> returns only newer segments (for catching up after a reconnect)."""
        qs = self.get_object().segments.all()
        after = request.query_params.get("after")
        if after is not None and after.isdigit():
            qs = qs.filter(seq__gt=int(after))
        return Response(SegmentSerializer(qs, many=True).data)

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

    @action(detail=True, methods=["patch"], url_path=r"participants/(?P<label>[^/]+)")
    def participant(self, request, pk=None, label=None):
        """Name a speaker, e.g. PATCH /calls/<id>/participants/A/ {"display_name": "Marie"}."""
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


class AllowedNumberViewSet(viewsets.ModelViewSet):
    serializer_class = AllowedNumberSerializer

    def get_queryset(self):
        return AllowedNumber.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class DeviceView(APIView):
    """Register or refresh this phone's FCM token."""

    def post(self, request):
        ser = DeviceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        Device.objects.update_or_create(
            token=ser.validated_data["token"],
            defaults={"user": request.user, "platform": ser.validated_data["platform"]},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
