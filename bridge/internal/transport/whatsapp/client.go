// Package whatsapp implements CallTransport using whatsmeow + meowcaller.
//
// whatsmeow carries call signalling only; meowcaller supplies the media stack
// (MLow codec, SRTP, RTP, relay). The library requires meowcaller to be
// attached BEFORE Connect starts the receive loop — New() does this so every
// caller of Connect is safe by construction.
package whatsapp

import (
	"context"
	"fmt"
	"log/slog"
	"os"

	"github.com/mdp/qrterminal/v3"
	"github.com/purpshell/meowcaller"
	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/store/sqlstore"
	"go.mau.fi/whatsmeow/types/events"
	waLog "go.mau.fi/whatsmeow/util/log"
	_ "modernc.org/sqlite" // registers "sqlite" driver (pure Go, no CGO)
)

// Client wraps a paired whatsmeow session and the meowcaller voice stack.
// All exported methods are safe for concurrent use.
type Client struct {
	wa     *whatsmeow.Client
	Caller *meowcaller.Client // exported so session layer can register call handlers
	log    *slog.Logger
}

// New opens (or creates) the SQLite store at dbPath, restores the paired
// session if one exists, and attaches the meowcaller voice stack. Connect must
// be called to bring the session online.
func New(dbPath string, log *slog.Logger) (*Client, error) {
	container, err := sqlstore.New("sqlite", "file:"+dbPath+"?_foreign_keys=on", waLog.Stdout("WA-DB", "ERROR", false))
	if err != nil {
		return nil, fmt.Errorf("open store: %w", err)
	}

	device, err := container.GetFirstDevice()
	if err != nil {
		return nil, fmt.Errorf("get device: %w", err)
	}

	wa := whatsmeow.NewClient(device, waLog.Stdout("WA", "ERROR", false))

	// meowcaller MUST be attached before Connect; New() is the only path to a
	// Client, so this invariant is always satisfied.
	caller := meowcaller.NewClient(wa)

	return &Client{wa: wa, Caller: caller, log: log}, nil
}

// AddEventHandler registers a raw whatsmeow event handler and returns its ID.
// Must be called before Connect so the handler catches the connected event.
func (c *Client) AddEventHandler(fn func(any)) uint32 {
	return c.wa.AddEventHandler(fn)
}

// Connect brings the session online. If the number has never been paired it
// starts an interactive QR flow and blocks until the scan succeeds, fails, or
// ctx is cancelled. If already paired it reconnects immediately.
func (c *Client) Connect(ctx context.Context) error {
	if c.wa.Store.ID != nil {
		if err := c.wa.Connect(); err != nil {
			return fmt.Errorf("reconnect: %w", err)
		}
		return nil
	}
	return c.pairQR(ctx)
}

func (c *Client) pairQR(ctx context.Context) error {
	qrChan, err := c.wa.GetQRChannel(ctx)
	if err != nil {
		return fmt.Errorf("get qr channel: %w", err)
	}
	if err := c.wa.Connect(); err != nil {
		return fmt.Errorf("connect for pairing: %w", err)
	}
	c.log.Info("waiting for QR scan",
		"instructions", "WhatsApp → ⋮ menu → Linked Devices → Link a Device",
	)
	for evt := range qrChan {
		switch evt.Event {
		case "code":
			fmt.Fprintln(os.Stdout) // blank line before QR block
			qrterminal.GenerateHalfBlock(evt.Code, qrterminal.L, os.Stdout)
			c.log.Info("QR code displayed — scan within 60 s")
		case "success":
			c.log.Info("pairing successful")
			return nil
		case "timeout":
			return fmt.Errorf("QR pairing timed out — restart to get a fresh code")
		default:
			c.log.Info("pairing event", "event", evt.Event)
		}
	}
	return nil
}

// Disconnect cleanly tears down the session.
func (c *Client) Disconnect() {
	c.wa.Disconnect()
}

// IsLoggedIn reports whether the session is currently connected and authenticated.
func (c *Client) IsLoggedIn() bool {
	return c.wa.IsLoggedIn()
}

// TextFrom extracts plain text from a message, trying the most common types.
// Returns an empty string for non-text messages (images, stickers, etc.).
func TextFrom(msg *events.Message) string {
	if t := msg.Message.GetConversation(); t != "" {
		return t
	}
	if t := msg.Message.GetExtendedTextMessage().GetText(); t != "" {
		return t
	}
	return ""
}
