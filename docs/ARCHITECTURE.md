# Architecture

## Overview

Clippy is a bot that joins WhatsApp calls as a participant, transcribes speech in real time with speaker attribution, and responds when addressed by name.

## Components

```
┌──────────────────────────────────────┐
│  bridge/  (Go)                       │
│                                      │
│  cmd/clippy        entry point       │
│  internal/                           │
│    config/         env-var loading   │
│    transport/      CallTransport IF  │
│      whatsapp/     whatsmeow impl    │
│    stt/            STT IF            │
│      assemblyai/   streaming impl    │
│    tts/            TTS IF            │
│    llm/            LLM IF            │
│      anthropic/    Claude impl       │
│    session/        per-call state    │
└────────────┬─────────────────────────┘
             │ REST + WebSocket (X-Bridge-Key)
┌────────────▼─────────────────────────┐
│  backend/  (Django + Channels)       │
│                                      │
│  core/     User, SocialAccount       │
│  calls/    Call, Transcript, Notes   │
│            WebSocket live feed       │
└────────────┬─────────────────────────┘
             │ JWT REST + WebSocket
┌────────────▼─────────────────────────┐
│  app/  (React Native — phase 3)      │
└──────────────────────────────────────┘
```

## Bridge call flow

1. User adds the bot's WhatsApp number to an existing call.
2. `meowcaller` fires a call-invite event; the bridge checks the adder against the allowlist via `POST /bridge/calls/`.
3. Backend returns the call UUID and trigger name; bridge joins the call and announces the consent notice (TTS).
4. Audio frames arrive via `CallTransport.Connect`; the bridge streams PCM to the STT provider.
5. Each final `stt.Segment` is posted to `POST /bridge/calls/<id>/segments/`.
6. `LLM.ShouldReply` gates each utterance; if addressed, the reply is spoken (TTS → `SendAudio`) and logged as a note.
7. On call end, `LLM.Summarize` writes a summary to disk and posts it to `POST /bridge/calls/<id>/end/`.

## Key design decisions

- **No CGO, pure-Go SQLite** (`modernc.org/sqlite`) so the bridge builds on Windows without a C toolchain.
- **Platform behind an interface** (`CallTransport`) so WhatsApp can be replaced without touching STT/TTS/LLM.
- **Allowlist enforced at two points**: bridge checks before joining, backend returns 403 as a second gate.
- Phone numbers are redacted in all log output.
