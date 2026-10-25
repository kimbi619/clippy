# Clippy API Reference

Base URL: `http://localhost:8000` (development)

All app endpoints (except registration and token obtain) require:
```
Authorization: Bearer <access_token>
```

---

## Authentication

### Register
`POST /api/auth/register/`

**No auth required.**

```json
// Request
{
  "email": "alice@example.com",
  "first_name": "Alice",
  "last_name": "Smith",
  "phone_number": "+237600000001",   // optional, E.164
  "password": "StrongPass1!",
  "password_confirm": "StrongPass1!"
}

// Response 201
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "alice@example.com",
  "first_name": "Alice",
  "last_name": "Smith",
  "full_name": "Alice Smith",
  "phone_number": "+237600000001",
  "avatar_url": "",
  "date_joined": "2026-10-25T12:00:00Z"
}
```

---

### Obtain Tokens
`POST /api/auth/token/`

**No auth required.**

```json
// Request
{ "email": "alice@example.com", "password": "StrongPass1!" }

// Response 200
{ "access": "<jwt>", "refresh": "<jwt>" }
```

Access tokens expire after **60 minutes**. Refresh tokens expire after **7 days** and rotate on use.

---

### Refresh Token
`POST /api/auth/token/refresh/`

**No auth required.**

```json
// Request
{ "refresh": "<refresh_token>" }

// Response 200
{ "access": "<new_access_token>" }
```

---

### Get / Update Profile
`GET /api/me/` — returns the authenticated user's profile.

`PATCH /api/me/` — updates `first_name`, `last_name`, `phone_number`, `avatar_url`. Email is read-only.

```json
// PATCH request
{ "first_name": "Alicia" }

// Response 200
{
  "id": "...",
  "email": "alice@example.com",
  "first_name": "Alicia",
  "last_name": "Smith",
  "full_name": "Alicia Smith",
  "phone_number": "+237600000001",
  "avatar_url": "",
  "date_joined": "2026-10-25T12:00:00Z"
}
```

---

### Change Password
`POST /api/me/password/`

```json
// Request
{ "current_password": "OldPass1!", "new_password": "NewPass2!" }

// Response 204 No Content
```

---

## Calls

### List Calls
`GET /api/calls/`

Returns all calls owned by the authenticated user, newest first.

```json
// Response 200
[
  {
    "id": "550e8400-...",
    "platform": "whatsapp",
    "status": "active",          // active | ended
    "started_at": "2026-10-25T10:00:00Z",
    "ended_at": null,
    "summary": ""
  }
]
```

---

### Get Call Detail
`GET /api/calls/{id}/`

Includes full participant list and notes.

```json
// Response 200
{
  "id": "550e8400-...",
  "platform": "whatsapp",
  "status": "ended",
  "started_at": "2026-10-25T10:00:00Z",
  "ended_at": "2026-10-25T10:45:00Z",
  "summary": "Discussed Q4 roadmap...",
  "participants": [
    { "label": "A", "identifier": "", "display_name": "Alice" },
    { "label": "B", "identifier": "", "display_name": "" }
  ],
  "notes": [
    { "id": 1, "kind": "action_item", "text": "Send slides", "created_at": "..." }
  ]
}
```

---

### Delete Call
`DELETE /api/calls/{id}/` → `204 No Content`

---

### Get Transcript
`GET /api/calls/{id}/segments/`

Optional query param: `?after=<seq>` — returns only segments with `seq > after` (for reconnect catch-up).

```json
// Response 200
[
  { "seq": 1, "speaker": "A", "text": "Hello everyone", "start_ms": 0, "end_ms": 1200, "is_final": true },
  { "seq": 2, "speaker": "B", "text": "Thanks for joining", "start_ms": 1500, "end_ms": 3000, "is_final": true }
]
```

---

### Get / Add Notes
`GET /api/calls/{id}/notes/` — lists notes.

`POST /api/calls/{id}/notes/` — adds a manual note.

```json
// POST request
{ "kind": "note", "text": "Alice wants slides by EOD" }
// kind: note | action_item | reply

// Response 201
{ "id": 7, "kind": "note", "text": "Alice wants slides by EOD", "created_at": "..." }
```

---

### Name a Participant
`PATCH /api/calls/{id}/participants/{label}/`

Maps a speaker label from the STT diarizer to a display name.

```json
// PATCH request (label is "A", "B", etc.)
{ "display_name": "Alice" }

// Response 200
{ "label": "A", "identifier": "", "display_name": "Alice" }
```

---

## Settings

`GET /api/settings/` — retrieve bot settings for the authenticated user.

`PATCH /api/settings/` — update.

```json
// Response / PATCH body
{ "trigger_name": "Clippy" }   // the name participants say to address the bot
```

---

## Allowed Numbers

Numbers allowed to add the bot to a WhatsApp call. The bridge returns 403 and leaves if the adder isn't on this list.

`GET /api/allowlist/` — list own numbers.

`POST /api/allowlist/` — add a number.

```json
// POST request
{ "number": "+237600000001", "label": "My phone" }

// Response 201
{ "id": 3, "number": "+237600000001", "label": "My phone", "created_at": "..." }
```

`GET /api/allowlist/{id}/` · `PATCH /api/allowlist/{id}/` · `DELETE /api/allowlist/{id}/`

Numbers must be in **E.164 format** (`+` followed by 7–15 digits, no spaces).

---

## Device Registration (FCM Push)

`POST /api/devices/`

Register or refresh an FCM token so the backend can push call events to the mobile app.

```json
// Request
{ "token": "fcm-registration-token", "platform": "android" }
// platform: android | ios

// Response 204 No Content
```

Sending the same token again updates the owning user (safe for token refresh).

---

## WebSocket — Live Call Feed

`ws://host/ws/calls/{call_id}/`

**Auth:** `Authorization: Bearer <token>` header, or `?token=<token>` query param on the handshake.

The server sends JSON frames:

```json
{ "event": "segments", "data": [ { "seq": 3, "speaker": "A", "text": "..." } ] }
{ "event": "note",     "data": { "id": 8, "kind": "note", "text": "..." } }
{ "event": "call_ended","data": { "ended_at": "...", "summary": "..." } }
```

Close code `4403` — not authenticated or not the call owner.

Use `GET /api/calls/{id}/segments/?after=<last_seq>` to catch up after a reconnect.

---

## Bridge API (internal — Go bridge only)

All bridge endpoints require the `X-Bridge-Key` header matching `BRIDGE_API_KEY` in the backend environment. No user auth.

### Start Call
`POST /bridge/calls/`

Called when the bot is added to a call. Returns `403` if `added_by` is not on the allowlist — the bridge must leave the call on 403.

```json
// Request
{ "added_by": "+237600000001", "platform": "whatsapp", "external_id": "WA-CALL-XYZ" }

// Response 201 (new call) or 200 (retry, same external_id)
{ "id": "550e8400-...", "trigger_name": "Clippy" }
```

### Post Segments
`POST /bridge/calls/{id}/segments/`

Batch upsert. Re-sending a `seq` overwrites the row (use to upgrade interim → final).

```json
// Request — array of segments
[
  { "seq": 1, "speaker": "A", "text": "Hello", "start_ms": 0, "end_ms": 800, "is_final": true }
]

// Response 200
{ "count": 1 }
```

### Post Note
`POST /bridge/calls/{id}/notes/`

```json
// Request
{ "kind": "reply", "text": "Sure, I can summarize that." }

// Response 201
{ "id": 5, "kind": "reply", "text": "...", "created_at": "..." }
```

### End Call
`POST /bridge/calls/{id}/end/`

Safe to call twice. First call sets `ended_at`; subsequent calls are no-ops.

```json
// Request
{ "summary": "Discussed Q4 roadmap and assigned action items." }

// Response 204 No Content
```
