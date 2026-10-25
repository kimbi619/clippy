// Package tts defines the text-to-speech interface.
package tts

import (
	"context"
	"io"
)

// TTS converts text to PCM audio suitable for SendAudio.
type TTS interface {
	// Synthesize returns a stream of raw PCM (int16, little-endian).
	// The caller must close the reader when done.
	Synthesize(ctx context.Context, text string) (io.ReadCloser, sampleRate int, err error)
}
