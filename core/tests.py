from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


# ── helpers ──────────────────────────────────────────────────────────────────

def make_user(**kwargs):
    kwargs.setdefault("email", "alice@example.com")
    kwargs.setdefault("first_name", "Alice")
    kwargs.setdefault("last_name", "Smith")
    kwargs.setdefault("password", "S3cr3tPass!")
    return User.objects.create_user(**kwargs)


def auth_client(user):
    """Return an APIClient pre-loaded with a valid JWT for *user*."""
    refresh = RefreshToken.for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return c


# ── User model & manager ──────────────────────────────────────────────────────

class UserManagerTest(APITestCase):
    def test_create_user_requires_email(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password="pass")

    def test_create_user(self):
        u = make_user(email="bob@example.com")
        self.assertEqual(u.email, "bob@example.com")
        self.assertTrue(u.check_password("S3cr3tPass!"))
        self.assertFalse(u.is_staff)
        self.assertFalse(u.is_superuser)
        self.assertTrue(u.is_active)

    def test_create_superuser(self):
        u = User.objects.create_superuser("admin@example.com", "adminpass")
        self.assertTrue(u.is_staff)
        self.assertTrue(u.is_superuser)

    def test_email_is_normalized(self):
        u = User.objects.create_user(
            email="Bob@EXAMPLE.COM", first_name="Bob", last_name="X", password="pass"
        )
        self.assertEqual(u.email, "Bob@example.com")


class UserModelTest(APITestCase):
    def test_full_name(self):
        u = make_user(first_name="Ada", last_name="Lovelace")
        self.assertEqual(u.full_name, "Ada Lovelace")

    def test_str(self):
        u = make_user(email="str@example.com")
        self.assertEqual(str(u), "str@example.com")

    def test_uuid_pk(self):
        import uuid
        u = make_user(email="uuid@example.com")
        self.assertIsInstance(u.pk, uuid.UUID)


# ── POST /api/auth/register/ ──────────────────────────────────────────────────

class RegisterViewTest(APITestCase):
    url = "/api/auth/register/"

    def test_success(self):
        r = self.client.post(self.url, {
            "email": "new@example.com",
            "first_name": "New",
            "last_name": "User",
            "password": "StrongPass1!",
            "password_confirm": "StrongPass1!",
        }, format="json")
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertEqual(data["email"], "new@example.com")
        self.assertNotIn("password", data)
        self.assertIn("id", data)

    def test_duplicate_email(self):
        make_user(email="dup@example.com")
        r = self.client.post(self.url, {
            "email": "dup@example.com",
            "first_name": "Dup", "last_name": "User",
            "password": "StrongPass1!", "password_confirm": "StrongPass1!",
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_password_mismatch(self):
        r = self.client.post(self.url, {
            "email": "mismatch@example.com",
            "first_name": "X", "last_name": "Y",
            "password": "StrongPass1!", "password_confirm": "DifferentPass!",
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("password_confirm", r.json())

    def test_weak_password_rejected(self):
        r = self.client.post(self.url, {
            "email": "weak@example.com",
            "first_name": "W", "last_name": "P",
            "password": "123", "password_confirm": "123",
        }, format="json")
        self.assertEqual(r.status_code, 400)


# ── POST /api/auth/token/ and /api/auth/token/refresh/ ───────────────────────

class TokenViewTest(APITestCase):
    def setUp(self):
        self.user = make_user(email="jwt@example.com", password="TestPass99!")

    def test_obtain_token(self):
        r = self.client.post("/api/auth/token/", {
            "email": "jwt@example.com",
            "password": "TestPass99!",
        }, format="json")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("access", data)
        self.assertIn("refresh", data)

    def test_wrong_password_is_401(self):
        r = self.client.post("/api/auth/token/", {
            "email": "jwt@example.com",
            "password": "wrongpass",
        }, format="json")
        self.assertEqual(r.status_code, 401)

    def test_unknown_email_is_401(self):
        r = self.client.post("/api/auth/token/", {
            "email": "nobody@example.com",
            "password": "TestPass99!",
        }, format="json")
        self.assertEqual(r.status_code, 401)

    def test_refresh(self):
        r1 = self.client.post("/api/auth/token/", {
            "email": "jwt@example.com", "password": "TestPass99!",
        }, format="json")
        r2 = self.client.post("/api/auth/token/refresh/", {
            "refresh": r1.json()["refresh"],
        }, format="json")
        self.assertEqual(r2.status_code, 200)
        self.assertIn("access", r2.json())


# ── GET|PATCH /api/me/ ────────────────────────────────────────────────────────

class ProfileViewTest(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.c = auth_client(self.user)

    def test_get_profile(self):
        r = self.c.get("/api/me/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["email"], self.user.email)
        self.assertEqual(data["full_name"], self.user.full_name)
        self.assertNotIn("password", data)

    def test_patch_first_name(self):
        r = self.c.patch("/api/me/", {"first_name": "Updated"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["first_name"], "Updated")

    def test_email_is_read_only(self):
        r = self.c.patch("/api/me/", {"email": "hacked@evil.com"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "alice@example.com")

    def test_unauthenticated_is_401(self):
        r = self.client.get("/api/me/")
        self.assertEqual(r.status_code, 401)

    def test_invalid_token_is_401(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer not.a.real.token")
        r = c.get("/api/me/")
        self.assertEqual(r.status_code, 401)


# ── POST /api/me/password/ ────────────────────────────────────────────────────

class ChangePasswordViewTest(APITestCase):
    url = "/api/me/password/"

    def setUp(self):
        self.user = make_user(password="OldPass123!")
        self.c = auth_client(self.user)

    def test_change_password(self):
        r = self.c.post(self.url, {
            "current_password": "OldPass123!",
            "new_password": "NewPass456!",
        }, format="json")
        self.assertEqual(r.status_code, 204)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPass456!"))

    def test_wrong_current_password(self):
        r = self.c.post(self.url, {
            "current_password": "WrongPass!",
            "new_password": "NewPass456!",
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("current_password", r.json())

    def test_unauthenticated_is_401(self):
        r = self.client.post(self.url, {
            "current_password": "OldPass123!",
            "new_password": "NewPass456!",
        }, format="json")
        self.assertEqual(r.status_code, 401)
