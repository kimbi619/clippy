from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from calls.models import AllowedNumber, Call, Device, TranscriptSegment, UserSettings

User = get_user_model()
BRIDGE_KEY = "test-bridge-secret"


# ── helpers ──────────────────────────────────────────────────────────────────

def make_user(**kwargs):
    kwargs.setdefault("email", "alice@example.com")
    kwargs.setdefault("first_name", "Alice")
    kwargs.setdefault("last_name", "Smith")
    kwargs.setdefault("password", "S3cr3tPass!")
    return User.objects.create_user(**kwargs)


def auth_client(user):
    refresh = RefreshToken.for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return c


def bridge_client():
    c = APIClient()
    c.credentials(HTTP_X_BRIDGE_KEY=BRIDGE_KEY)
    return c


# ── Bridge authentication ─────────────────────────────────────────────────────

@override_settings(BRIDGE_API_KEY=BRIDGE_KEY)
class BridgeKeyAuthTest(APITestCase):
    def test_no_key_is_403(self):
        r = self.client.post("/bridge/calls/", {}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_wrong_key_is_403(self):
        c = APIClient()
        c.credentials(HTTP_X_BRIDGE_KEY="wrong-key")
        r = c.post("/bridge/calls/", {}, format="json")
        self.assertEqual(r.status_code, 403)


# ── Bridge: call start ────────────────────────────────────────────────────────

@override_settings(BRIDGE_API_KEY=BRIDGE_KEY)
class BridgeCallStartTest(APITestCase):
    def setUp(self):
        self.user = make_user()
        AllowedNumber.objects.create(owner=self.user, number="+237600000001")
        self.bc = bridge_client()

    def test_allowed_number_creates_call(self):
        r = self.bc.post("/bridge/calls/", {
            "added_by": "+237600000001",
            "platform": "whatsapp",
            "external_id": "call-abc-001",
        }, format="json")
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertIn("id", data)
        self.assertIn("trigger_name", data)
        self.assertTrue(Call.objects.filter(pk=data["id"]).exists())

    def test_disallowed_number_is_403(self):
        r = self.bc.post("/bridge/calls/", {
            "added_by": "+237600000099",
        }, format="json")
        self.assertEqual(r.status_code, 403)

    def test_retry_with_same_external_id_returns_200(self):
        payload = {
            "added_by": "+237600000001",
            "platform": "whatsapp",
            "external_id": "call-retry-001",
        }
        r1 = self.bc.post("/bridge/calls/", payload, format="json")
        r2 = self.bc.post("/bridge/calls/", payload, format="json")
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.json()["id"], r2.json()["id"])
        self.assertEqual(Call.objects.filter(external_id="call-retry-001").count(), 1)

    def test_call_owner_matches_allowed_number_owner(self):
        r = self.bc.post("/bridge/calls/", {"added_by": "+237600000001"}, format="json")
        call = Call.objects.get(pk=r.json()["id"])
        self.assertEqual(call.owner, self.user)

    def test_trigger_name_from_user_settings(self):
        UserSettings.objects.update_or_create(
            user=self.user, defaults={"trigger_name": "Jarvis"}
        )
        r = self.bc.post("/bridge/calls/", {"added_by": "+237600000001"}, format="json")
        self.assertEqual(r.json()["trigger_name"], "Jarvis")

    def test_default_trigger_name_is_clippy(self):
        r = self.bc.post("/bridge/calls/", {"added_by": "+237600000001"}, format="json")
        self.assertEqual(r.json()["trigger_name"], "Clippy")


# ── Bridge: transcript segments ───────────────────────────────────────────────

@override_settings(BRIDGE_API_KEY=BRIDGE_KEY)
class BridgeSegmentsTest(APITestCase):
    def setUp(self):
        self.user = make_user()
        AllowedNumber.objects.create(owner=self.user, number="+237600000001")
        r = bridge_client().post("/bridge/calls/", {"added_by": "+237600000001"}, format="json")
        self.call_id = r.json()["id"]
        self.url = f"/bridge/calls/{self.call_id}/segments/"
        self.bc = bridge_client()

    @patch("calls.events.publish")
    def test_add_segments(self, _pub):
        r = self.bc.post(self.url, [
            {"seq": 1, "speaker": "A", "text": "Hello", "start_ms": 0, "end_ms": 500, "is_final": True},
            {"seq": 2, "speaker": "B", "text": "World", "start_ms": 600, "end_ms": 1000, "is_final": False},
        ], format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 2)
        self.assertEqual(TranscriptSegment.objects.filter(call_id=self.call_id).count(), 2)

    @patch("calls.events.publish")
    def test_resend_seq_overwrites_interim(self, _pub):
        self.bc.post(self.url, [
            {"seq": 1, "text": "interim", "start_ms": 0, "end_ms": 0, "is_final": False},
        ], format="json")
        self.bc.post(self.url, [
            {"seq": 1, "text": "final text", "start_ms": 0, "end_ms": 800, "is_final": True},
        ], format="json")
        segs = TranscriptSegment.objects.filter(call_id=self.call_id, seq=1)
        self.assertEqual(segs.count(), 1)
        self.assertEqual(segs.first().text, "final text")
        self.assertTrue(segs.first().is_final)

    @patch("calls.events.publish")
    def test_segments_auto_create_participants(self, _pub):
        self.bc.post(self.url, [
            {"seq": 1, "speaker": "A", "text": "hi", "start_ms": 0, "end_ms": 0, "is_final": True},
            {"seq": 2, "speaker": "B", "text": "hey", "start_ms": 0, "end_ms": 0, "is_final": True},
        ], format="json")
        call = Call.objects.get(pk=self.call_id)
        self.assertTrue(call.participants.filter(label="A").exists())
        self.assertTrue(call.participants.filter(label="B").exists())

    @patch("calls.events.publish")
    def test_publish_called_on_non_empty_batch(self, mock_pub):
        self.bc.post(self.url, [
            {"seq": 1, "text": "hi", "start_ms": 0, "end_ms": 0, "is_final": True},
        ], format="json")
        mock_pub.assert_called_once()


# ── Bridge: notes ─────────────────────────────────────────────────────────────

@override_settings(BRIDGE_API_KEY=BRIDGE_KEY)
class BridgeNoteTest(APITestCase):
    def setUp(self):
        self.user = make_user()
        AllowedNumber.objects.create(owner=self.user, number="+237600000001")
        r = bridge_client().post("/bridge/calls/", {"added_by": "+237600000001"}, format="json")
        self.call_id = r.json()["id"]
        self.bc = bridge_client()

    @patch("calls.events.publish")
    def test_add_note(self, _pub):
        r = self.bc.post(f"/bridge/calls/{self.call_id}/notes/", {
            "kind": "note",
            "text": "Follow up on action items",
        }, format="json")
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertEqual(data["text"], "Follow up on action items")
        self.assertEqual(data["kind"], "note")

    @patch("calls.events.publish")
    def test_add_action_item(self, _pub):
        r = self.bc.post(f"/bridge/calls/{self.call_id}/notes/", {
            "kind": "action_item",
            "text": "Send proposal by Friday",
        }, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["kind"], "action_item")


# ── Bridge: call end ──────────────────────────────────────────────────────────

@override_settings(BRIDGE_API_KEY=BRIDGE_KEY)
class BridgeCallEndTest(APITestCase):
    def setUp(self):
        self.user = make_user()
        AllowedNumber.objects.create(owner=self.user, number="+237600000001")
        r = bridge_client().post("/bridge/calls/", {"added_by": "+237600000001"}, format="json")
        self.call_id = r.json()["id"]
        self.bc = bridge_client()

    @patch("calls.events.publish")
    def test_end_call_with_summary(self, _pub):
        r = self.bc.post(f"/bridge/calls/{self.call_id}/end/", {
            "summary": "Discussed Q4 roadmap.",
        }, format="json")
        self.assertEqual(r.status_code, 204)
        call = Call.objects.get(pk=self.call_id)
        self.assertEqual(call.status, Call.Status.ENDED)
        self.assertEqual(call.summary, "Discussed Q4 roadmap.")
        self.assertIsNotNone(call.ended_at)

    @patch("calls.events.publish")
    def test_end_call_is_idempotent(self, _pub):
        url = f"/bridge/calls/{self.call_id}/end/"
        r1 = self.bc.post(url, {}, format="json")
        r2 = self.bc.post(url, {}, format="json")
        self.assertEqual(r1.status_code, 204)
        self.assertEqual(r2.status_code, 204)
        self.assertEqual(
            Call.objects.filter(pk=self.call_id, status=Call.Status.ENDED).count(), 1
        )

    @patch("calls.events.publish")
    def test_first_end_reason_wins(self, _pub):
        url = f"/bridge/calls/{self.call_id}/end/"
        self.bc.post(url, {}, format="json")
        ended_at_first = Call.objects.get(pk=self.call_id).ended_at
        self.bc.post(url, {}, format="json")
        ended_at_second = Call.objects.get(pk=self.call_id).ended_at
        self.assertEqual(ended_at_first, ended_at_second)


# ── Calls REST API ────────────────────────────────────────────────────────────

@override_settings(BRIDGE_API_KEY=BRIDGE_KEY)
class CallViewSetTest(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.other = make_user(email="other@example.com")
        AllowedNumber.objects.create(owner=self.user, number="+237600000001")
        r = bridge_client().post("/bridge/calls/", {"added_by": "+237600000001"}, format="json")
        self.call_id = r.json()["id"]
        self.c = auth_client(self.user)

    def test_list_returns_own_calls_only(self):
        r = self.c.get("/api/calls/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)

    def test_other_user_sees_empty_list(self):
        r = auth_client(self.other).get("/api/calls/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 0)

    def test_retrieve_includes_participants_and_notes(self):
        r = self.c.get(f"/api/calls/{self.call_id}/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("participants", data)
        self.assertIn("notes", data)

    def test_other_user_cannot_retrieve(self):
        r = auth_client(self.other).get(f"/api/calls/{self.call_id}/")
        self.assertEqual(r.status_code, 404)

    def test_unauthenticated_is_401(self):
        r = self.client.get("/api/calls/")
        self.assertEqual(r.status_code, 401)

    @patch("calls.events.publish")
    def test_segments_endpoint(self, _pub):
        bridge_client().post(f"/bridge/calls/{self.call_id}/segments/", [
            {"seq": 1, "speaker": "A", "text": "hello", "start_ms": 0, "end_ms": 0, "is_final": True},
        ], format="json")
        r = self.c.get(f"/api/calls/{self.call_id}/segments/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)

    @patch("calls.events.publish")
    def test_segments_after_filter(self, _pub):
        bridge_client().post(f"/bridge/calls/{self.call_id}/segments/", [
            {"seq": 1, "text": "a", "start_ms": 0, "end_ms": 0, "is_final": True},
            {"seq": 2, "text": "b", "start_ms": 0, "end_ms": 0, "is_final": True},
            {"seq": 3, "text": "c", "start_ms": 0, "end_ms": 0, "is_final": True},
        ], format="json")
        r = self.c.get(f"/api/calls/{self.call_id}/segments/?after=1")
        self.assertEqual(len(r.json()), 2)

    @patch("calls.events.publish")
    def test_post_note(self, _pub):
        r = self.c.post(f"/api/calls/{self.call_id}/notes/", {
            "kind": "action_item", "text": "Send slides",
        }, format="json")
        self.assertEqual(r.status_code, 201)


# ── Participant naming ────────────────────────────────────────────────────────

@override_settings(BRIDGE_API_KEY=BRIDGE_KEY)
class ParticipantTest(APITestCase):
    def setUp(self):
        self.user = make_user()
        AllowedNumber.objects.create(owner=self.user, number="+237600000001")
        r = bridge_client().post("/bridge/calls/", {"added_by": "+237600000001"}, format="json")
        self.call_id = r.json()["id"]
        with patch("calls.events.publish"):
            bridge_client().post(f"/bridge/calls/{self.call_id}/segments/", [
                {"seq": 1, "speaker": "A", "text": "hi", "start_ms": 0, "end_ms": 0, "is_final": True},
            ], format="json")
        self.c = auth_client(self.user)

    def test_name_participant(self):
        r = self.c.patch(f"/api/calls/{self.call_id}/participants/A/", {
            "display_name": "Alice",
        }, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["display_name"], "Alice")

    def test_unknown_participant_is_404(self):
        r = self.c.patch(f"/api/calls/{self.call_id}/participants/Z/", {
            "display_name": "Nobody",
        }, format="json")
        self.assertEqual(r.status_code, 404)


# ── Settings ──────────────────────────────────────────────────────────────────

class SettingsViewTest(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.c = auth_client(self.user)

    def test_get_defaults(self):
        r = self.c.get("/api/settings/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["trigger_name"], "Clippy")

    def test_update_trigger_name(self):
        r = self.c.patch("/api/settings/", {"trigger_name": "Jarvis"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["trigger_name"], "Jarvis")

    def test_unauthenticated_is_401(self):
        r = self.client.get("/api/settings/")
        self.assertEqual(r.status_code, 401)


# ── Allowlist ─────────────────────────────────────────────────────────────────

class AllowedNumberViewSetTest(APITestCase):
    url = "/api/allowlist/"

    def setUp(self):
        self.user = make_user()
        self.c = auth_client(self.user)

    def test_create(self):
        r = self.c.post(self.url, {"number": "+237600000001", "label": "My phone"}, format="json")
        self.assertEqual(r.status_code, 201)

    def test_list_own_only(self):
        AllowedNumber.objects.create(owner=self.user, number="+237600000001")
        other = make_user(email="other@example.com")
        AllowedNumber.objects.create(owner=other, number="+237600000099")
        r = self.c.get(self.url)
        self.assertEqual(len(r.json()), 1)

    def test_invalid_e164_rejected(self):
        r = self.c.post(self.url, {"number": "0600000001"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_delete(self):
        num = AllowedNumber.objects.create(owner=self.user, number="+237600000001")
        r = self.c.delete(f"{self.url}{num.pk}/")
        self.assertEqual(r.status_code, 204)
        self.assertFalse(AllowedNumber.objects.filter(pk=num.pk).exists())

    def test_unauthenticated_is_401(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 401)


# ── Device registration ───────────────────────────────────────────────────────

class DeviceViewTest(APITestCase):
    url = "/api/devices/"

    def setUp(self):
        self.user = make_user()
        self.c = auth_client(self.user)

    def test_register_android(self):
        r = self.c.post(self.url, {"token": "fcm-token-abc", "platform": "android"}, format="json")
        self.assertEqual(r.status_code, 204)
        self.assertTrue(Device.objects.filter(token="fcm-token-abc").exists())

    def test_register_ios(self):
        r = self.c.post(self.url, {"token": "apns-token-xyz", "platform": "ios"}, format="json")
        self.assertEqual(r.status_code, 204)

    def test_re_register_transfers_ownership(self):
        other = make_user(email="other@example.com")
        Device.objects.create(user=other, token="shared-token", platform="ios")
        r = self.c.post(self.url, {"token": "shared-token", "platform": "ios"}, format="json")
        self.assertEqual(r.status_code, 204)
        self.assertEqual(Device.objects.get(token="shared-token").user, self.user)

    def test_invalid_platform_rejected(self):
        r = self.c.post(self.url, {"token": "tok", "platform": "windows"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_unauthenticated_is_401(self):
        r = self.client.post(self.url, {"token": "tok", "platform": "android"}, format="json")
        self.assertEqual(r.status_code, 401)
