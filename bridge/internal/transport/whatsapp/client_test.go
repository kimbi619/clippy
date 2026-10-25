package whatsapp_test

import (
	"testing"

	waE2E "go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/types/events"
	"google.golang.org/protobuf/proto"

	"github.com/kimbi619/clippy/bridge/internal/transport/whatsapp"
)

func TestTextFrom_Conversation(t *testing.T) {
	msg := &events.Message{
		Message: &waE2E.Message{
			Conversation: proto.String("hello world"),
		},
	}
	got := whatsapp.TextFrom(msg)
	if got != "hello world" {
		t.Errorf("got %q, want %q", got, "hello world")
	}
}

func TestTextFrom_ExtendedText(t *testing.T) {
	msg := &events.Message{
		Message: &waE2E.Message{
			ExtendedTextMessage: &waE2E.ExtendedTextMessage{
				Text: proto.String("extended hello"),
			},
		},
	}
	got := whatsapp.TextFrom(msg)
	if got != "extended hello" {
		t.Errorf("got %q, want %q", got, "extended hello")
	}
}

func TestTextFrom_ConversationTakesPrecedence(t *testing.T) {
	msg := &events.Message{
		Message: &waE2E.Message{
			Conversation: proto.String("primary"),
			ExtendedTextMessage: &waE2E.ExtendedTextMessage{
				Text: proto.String("secondary"),
			},
		},
	}
	got := whatsapp.TextFrom(msg)
	if got != "primary" {
		t.Errorf("Conversation should win; got %q", got)
	}
}

func TestTextFrom_NonTextReturnsEmpty(t *testing.T) {
	msg := &events.Message{
		Message: &waE2E.Message{},
	}
	got := whatsapp.TextFrom(msg)
	if got != "" {
		t.Errorf("want empty string, got %q", got)
	}
}

func TestTextFrom_EmptyConversationFallsThrough(t *testing.T) {
	msg := &events.Message{
		Message: &waE2E.Message{
			Conversation: proto.String(""),
			ExtendedTextMessage: &waE2E.ExtendedTextMessage{
				Text: proto.String("fallback"),
			},
		},
	}
	got := whatsapp.TextFrom(msg)
	if got != "fallback" {
		t.Errorf("expected fallback to extended text; got %q", got)
	}
}
