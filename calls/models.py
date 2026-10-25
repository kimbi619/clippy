import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

E164 = RegexValidator(r"^\+[1-9]\d{6,14}$", "Use E.164, e.g. +237600000000")


class UserSettings(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="clippy_settings")
    trigger_name = models.CharField(max_length=50, default="Clippy")


class AllowedNumber(models.Model):
    """A phone number allowed to add the bot to a call. Globally unique so the
    bridge can resolve number -> owner."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="allowed_numbers")
    number = models.CharField(max_length=16, unique=True, validators=[E164])
    label = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Call(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        ENDED = "ended"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="calls")
    platform = models.CharField(max_length=32, default="whatsapp")
    external_id = models.CharField(max_length=128, blank=True)  # platform's call id
    added_by = models.CharField(max_length=16)  # E.164 of the person who added the bot
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    summary = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]


class Participant(models.Model):
    call = models.ForeignKey(Call, on_delete=models.CASCADE, related_name="participants")
    label = models.CharField(max_length=32)  # speaker label from STT, e.g. "A", or a number
    identifier = models.CharField(max_length=64, blank=True)  # platform id when known (group calls)
    display_name = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["call", "label"], name="uniq_participant_label")]


class TranscriptSegment(models.Model):
    call = models.ForeignKey(Call, on_delete=models.CASCADE, related_name="segments")
    seq = models.PositiveIntegerField()  # assigned by the bridge; re-sending a seq overwrites (interim -> final)
    speaker = models.CharField(max_length=32, blank=True)  # matches Participant.label
    text = models.TextField()
    start_ms = models.PositiveIntegerField(default=0)
    end_ms = models.PositiveIntegerField(default=0)
    is_final = models.BooleanField(default=False)

    class Meta:
        ordering = ["seq"]
        constraints = [models.UniqueConstraint(fields=["call", "seq"], name="uniq_segment_seq")]


class Note(models.Model):
    class Kind(models.TextChoices):
        NOTE = "note"
        ACTION_ITEM = "action_item"
        REPLY = "reply"  # something the bot said in the call

    call = models.ForeignKey(Call, on_delete=models.CASCADE, related_name="notes")
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.NOTE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class Device(models.Model):
    class Platform(models.TextChoices):
        IOS = "ios"
        ANDROID = "android"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="devices")
    token = models.CharField(max_length=255, unique=True)  # FCM registration token
    platform = models.CharField(max_length=8, choices=Platform.choices)
    created_at = models.DateTimeField(auto_now_add=True)
