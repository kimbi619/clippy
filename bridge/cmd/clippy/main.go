package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"go.mau.fi/whatsmeow/types/events"

	"github.com/kimbi619/clippy/bridge/internal/config"
	"github.com/kimbi619/clippy/bridge/internal/transport/whatsapp"
)

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))
	slog.SetDefault(log)

	cfg, err := config.Load()
	if err != nil {
		slog.Error("config", "err", err)
		os.Exit(1)
	}
	slog.Info("clippy starting",
		"backend", cfg.BackendURL,
		"phone", redact(cfg.WhatsAppPhone),
		"store", cfg.StorePath,
	)

	wa, err := whatsapp.New(cfg.StorePath, log)
	if err != nil {
		slog.Error("whatsapp init", "err", err)
		os.Exit(1)
	}

	// Register before Connect so we don't miss the Connected event.
	wa.AddEventHandler(func(evt any) {
		switch v := evt.(type) {
		case *events.Connected:
			slog.Info("session connected")
		case *events.Disconnected:
			slog.Info("session disconnected")
		case *events.Message:
			logMessage(v)
		}
	})

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	if err := wa.Connect(ctx); err != nil {
		slog.Error("connect", "err", err)
		os.Exit(1)
	}
	slog.Info("connected — send a message to the bot number to test (Milestone 1 done when you see a 'message' log line)")

	<-ctx.Done()
	slog.Info("shutting down")
	wa.Disconnect()
}

func logMessage(msg *events.Message) {
	text := whatsapp.TextFrom(msg)
	slog.Info("message",
		"from", redact(msg.Info.Sender.User),
		"chat", msg.Info.Chat.String(),
		"group", msg.Info.IsGroup,
		"text", text,
	)
}

// redact replaces the middle digits of a phone/JID user part so it is safe to log.
func redact(phone string) string {
	if len(phone) < 7 {
		return "***"
	}
	return phone[:3] + "****" + phone[len(phone)-3:]
}
