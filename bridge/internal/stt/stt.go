// Package stt defines the streaming speech-to-text interface.
// Default implementation: AssemblyAI (streaming + speaker diarization).
package stt

import "context"

// Segment is one transcript chunk from the STT provider.
type Segment struct {
	Speaker string // label from diarization, e.g. "A", "B"
	Text    string
	StartMS uint32
	EndMS   uint32
	IsFinal bool // false while the provider may still revise this segment
}

// STT streams PCM audio and emits transcript segments with speaker labels.
// Implementations must close the returned channel when the context is cancelled
// or an unrecoverable error occurs.
type STT interface {
	Stream(ctx context.Context, audio <-chan []int16, sampleRate int) (<-chan Segment, error)
}
