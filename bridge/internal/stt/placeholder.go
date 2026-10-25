package stt

import (
	"context"
	"fmt"
	"time"
)

// Placeholder drains the audio channel and emits one fake segment every
// 5 seconds so the rest of the pipeline has something to process.
// Replace with an AssemblyAI (or Whisper/Deepgram) implementation for real transcription.
type Placeholder struct{}

func NewPlaceholder() *Placeholder { return &Placeholder{} }

func (p *Placeholder) Stream(ctx context.Context, audio <-chan []int16, _ int) (<-chan Segment, error) {
	out := make(chan Segment, 8)
	go func() {
		defer close(out)
		seq := 0
		tick := time.NewTicker(5 * time.Second)
		defer tick.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case _, ok := <-audio:
				if !ok {
					return
				}
				// drain — real STT would accumulate PCM frames here
			case <-tick.C:
				seq++
				out <- Segment{
					Speaker: "A",
					Text:    fmt.Sprintf("[audio segment %d — transcription pending]", seq),
					StartMS: uint32((seq - 1) * 5000),
					EndMS:   uint32(seq * 5000),
					IsFinal: true,
				}
			}
		}
	}()
	return out, nil
}
