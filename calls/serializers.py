from rest_framework import serializers

from .models import AllowedNumber, Call, Device, Note, Participant, TranscriptSegment, UserSettings


class UserSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSettings
        fields = ["trigger_name"]


class AllowedNumberSerializer(serializers.ModelSerializer):
    class Meta:
        model = AllowedNumber
        fields = ["id", "number", "label", "created_at"]
        read_only_fields = ["id", "created_at"]


class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = ["token", "platform"]
        extra_kwargs = {"token": {"validators": []}}  # re-registering a token is an update, not an error


class ParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Participant
        fields = ["label", "identifier", "display_name"]
        read_only_fields = ["label", "identifier"]


class SegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TranscriptSegment
        fields = ["seq", "speaker", "text", "start_ms", "end_ms", "is_final"]


class NoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Note
        fields = ["id", "kind", "text", "created_at"]
        read_only_fields = ["id", "created_at"]


class CallListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Call
        fields = ["id", "platform", "status", "started_at", "ended_at", "summary"]


class CallDetailSerializer(CallListSerializer):
    participants = ParticipantSerializer(many=True, read_only=True)
    notes = NoteSerializer(many=True, read_only=True)

    class Meta(CallListSerializer.Meta):
        fields = CallListSerializer.Meta.fields + ["participants", "notes"]
