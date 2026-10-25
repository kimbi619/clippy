# Findings

Experiment results and known-unknown resolutions. Add an entry when you learn
something non-obvious about the libraries or the platform.

---

## Template

### [date] — [topic]

**Question:** what were you trying to find out?

**Method:** how did you test it?

**Result:** what happened?

**Impact:** what does this change about the implementation plan?

---

## Milestone 1 — manual test steps

1. Install Go 1.23+ (must be on PATH in PowerShell).
2. `cd bridge`
3. `go mod tidy` — fetches all deps, creates `go.sum`.
4. Copy `.env.example` to `.env`; set `BRIDGE_API_KEY` to any non-empty string for local testing.
5. `go run ./cmd/clippy`
6. On first run the bot is unpaired: a QR code prints to the terminal.
7. On the phone that will add the bot: open WhatsApp → ⋮ menu → **Linked Devices** → **Link a Device** → scan the QR.
8. The bridge logs `"pairing successful"` then `"connected"`.
9. From **any** phone, send a text message to the bot's number.
10. **Done when** the bridge prints a JSON log line with `"msg":"message"` containing the sender and text.

The session is saved to `whatsmeow.db` (gitignored). Subsequent runs skip the QR and reconnect directly.

**Windows PowerShell shortcut:**
```powershell
.\scripts\dev.ps1 run   # loads bridge/.env automatically
```

## Open questions

- Does `meowcaller` expose per-participant audio streams in group calls, or only a
  mixed stream? (The reference spec says per-participant is internal.)
- How is outbound audio fed into a call via `meowcaller`? The reference PR has no
  outbound implementation.
