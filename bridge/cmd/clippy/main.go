package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"go.mau.fi/whatsmeow/types/events"

	"github.com/kimbi619/clippy/bridge/internal/backend"
	"github.com/kimbi619/clippy/bridge/internal/config"
	"github.com/kimbi619/clippy/bridge/internal/llm"
	"github.com/kimbi619/clippy/bridge/internal/session"
	"github.com/kimbi619/clippy/bridge/internal/stt"
	"github.com/kimbi619/clippy/bridge/internal/transport/whatsapp"
)

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(log)

	cfg, err := config.Load()
	if err != nil {
		slog.Error("config", "err", err)
		os.Exit(1)
	}
	slog.Info("clippy starting",
		"backend", cfg.BackendURL,
		"store", cfg.StorePath,
	)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	wa, err := whatsapp.New(ctx, cfg.StorePath, log)
	if err != nil {
		slog.Error("whatsapp init", "err", err)
		os.Exit(1)
	}

	be := backend.New(cfg.BackendURL, cfg.BridgeAPIKey)
	mgr := session.NewManager(be, llm.NewPlaceholder(), stt.NewPlaceholder(), log)

	// Register event handler BEFORE Connect.
	wa.AddEventHandler(func(evt any) {
		switch v := evt.(type) {
		case *events.Connected:
			slog.Info("session connected", "jid", wa.JID())

		case *events.Disconnected:
			slog.Info("session disconnected")

		case *events.CallOffer:
			handleCallOffer(ctx, v, wa, mgr, log)

		case *events.CallTerminate:
			handleCallTerminate(ctx, v, mgr, log)

		case *events.Message:
			logMessage(v)
		}
	})

	if err := wa.Connect(ctx); err != nil {
		slog.Error("connect", "err", err)
		os.Exit(1)
	}
	slog.Info("ready — waiting for calls and messages")

	<-ctx.Done()
	slog.Info("shutting down")
	wa.Disconnect()
}

func handleCallOffer(ctx context.Context, v *events.CallOffer, wa *whatsapp.Client, mgr *session.Manager, log *slog.Logger) {
	addedBy := "+" + v.From.User
	log.Info("incoming call", "from", redact(v.From.User), "call_id", v.CallID)

	sess, err := mgr.Start(ctx, v.CallID, addedBy, "whatsapp")
	if err != nil {
		if err == backend.ErrNotAllowed {
			log.Warn("call rejected — number not on allowlist", "from", redact(v.From.User))
			// Reject the call via meowcaller so the caller knows we declined.
			if err := wa.Caller.RejectCall(v.From, v.CallID); err != nil {
				log.Error("reject call", "err", err)
			}
			return
		}
		log.Error("start call", "err", err)
		return
	}

	// Accept the call and get the audio stream.
	audioIn, err := wa.Caller.AcceptCall(v.From, v.CallID)
	if err != nil {
		log.Error("accept call", "err", err)
		mgr.End(ctx, v.CallID)
		return
	}
	log.Info("call accepted", "call_id", sess.CallID)

	// Run STT on audio in the background; each segment is forwarded to the session.
	go func() {
		callCtx, cancel := context.WithCancel(ctx)
		defer cancel()

		segCh, err := stt.NewPlaceholder().Stream(callCtx, audioIn, 16000)
		if err != nil {
			log.Error("stt stream", "err", err)
			return
		}
		for seg := range segCh {
			sess.HandleSegment(callCtx, seg)
		}
	}()
}

func handleCallTerminate(ctx context.Context, v *events.CallTerminate, mgr *session.Manager, log *slog.Logger) {
	log.Info("call terminated", "from", redact(v.From.User), "reason", v.Reason)
	mgr.End(ctx, v.CallID)
}

func logMessage(msg *events.Message) {
	text := whatsapp.TextFrom(msg)
	slog.Info("message",
		"from", redact(msg.Info.Sender.User),
		"text", text,
	)
}

func redact(phone string) string {
	if len(phone) < 7 {
		return "***"
	}
	return phone[:3] + "****" + phone[len(phone)-3:]
}
