package stt

import (
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"time"
)

// WhisperClient sends batched PCM audio to the local faster-whisper HTTP server
// and emits transcript segments. Audio is accumulated in chunkDur-sized windows
// before being sent, so latency ≈ chunkDur + inference time (~1-2s on CPU).
type WhisperClient struct {
	serverURL string
	chunkDur  time.Duration
	http      *http.Client
}

// NewWhisperClient creates an STT client that talks to a faster-whisper server.
// serverURL is the base URL, e.g. "http://localhost:8001".
// chunkDur controls how much audio is buffered before sending (e.g. 5s).
func NewWhisperClient(serverURL string, chunkDur time.Duration) *WhisperClient {
	return &WhisperClient{
		serverURL: serverURL,
		chunkDur:  chunkDur,
		http:      &http.Client{Timeout: 30 * time.Second},
	}
}

func (w *WhisperClient) Stream(ctx context.Context, audio <-chan []int16, sampleRate int) (<-chan Segment, error) {
	out := make(chan Segment, 8)
	go w.run(ctx, audio, sampleRate, out)
	return out, nil
}

func (w *WhisperClient) run(ctx context.Context, audio <-chan []int16, sampleRate int, out chan<- Segment) {
	defer close(out)

	samplesPerChunk := int(w.chunkDur.Seconds()) * sampleRate
	buf := make([]int16, 0, samplesPerChunk)
	var chunkStartMS uint32
	var elapsed uint32 // ms of audio accumulated in buf

	flush := func() {
		if len(buf) == 0 {
			return
		}
		slog.Info("stt: sending chunk", "samples", len(buf), "duration_ms", elapsed)
		text, err := w.transcribe(ctx, buf)
		if err != nil {
			slog.Warn("stt: transcribe error", "err", err)
		} else if text != "" {
			endMS := chunkStartMS + elapsed
			out <- Segment{
				Speaker: "A",
				Text:    text,
				StartMS: chunkStartMS,
				EndMS:   endMS,
				IsFinal: true,
			}
			chunkStartMS = endMS
		} else {
			slog.Info("stt: no speech detected in chunk")
		}
		buf = buf[:0]
		elapsed = 0
	}

	for {
		select {
		case <-ctx.Done():
			flush()
			return
		case frame, ok := <-audio:
			if !ok {
				flush()
				return
			}
			buf = append(buf, frame...)
			elapsed += uint32(len(frame)) * 1000 / uint32(sampleRate)
			if len(buf) >= samplesPerChunk {
				flush()
			}
		}
	}
}

type transcribeResponse struct {
	Text string `json:"text"`
}

func (w *WhisperClient) transcribe(ctx context.Context, samples []int16) (string, error) {
	// Encode int16 samples as little-endian bytes.
	pcm := make([]byte, len(samples)*2)
	for i, s := range samples {
		binary.LittleEndian.PutUint16(pcm[i*2:], uint16(s))
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, w.serverURL+"/transcribe", bytes.NewReader(pcm))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/octet-stream")

	resp, err := w.http.Do(req)
	if err != nil {
		return "", fmt.Errorf("stt request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("stt server: status %d", resp.StatusCode)
	}

	var result transcribeResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", fmt.Errorf("stt decode: %w", err)
	}
	return result.Text, nil
}
