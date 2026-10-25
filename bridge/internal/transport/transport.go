// Package transport defines the platform-agnostic interface for joining calls.
// The WhatsApp implementation (whatsmeow + meowcaller) lives in a sub-package;
// swap it out here to support other platforms without touching the rest of the bridge.
package transport

import "context"

// AudioFrame is a chunk of raw PCM audio from a single participant.
type AudioFrame struct {
	ParticipantID string // platform-specific identifier, empty when unknown
	PCM           []int16
	SampleRate    int // Hz, typically 8000 or 16000
}

// CallEvent is emitted for each state change in an active call.
type CallEvent struct {
	// Type is one of: "join", "leave", "audio", "ended"
	Type          string
	ParticipantID string
	Frame         *AudioFrame // non-nil only when Type == "audio"
}

// CallTransport is the one interface the rest of the bridge talks to.
// Implementations must be safe for concurrent use.
type CallTransport interface {
	// Connect authenticates with the platform and begins receiving events.
	// It blocks until the context is cancelled or a fatal error occurs.
	Connect(ctx context.Context, events chan<- CallEvent) error

	// Disconnect tears down the session gracefully.
	Disconnect() error

	// SendAudio pushes outbound PCM into the call.
	SendAudio(ctx context.Context, pcm []int16, sampleRate int) error
}
