package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"path/filepath"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/purpshell/meowcaller"
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
	slog.Info("clippy starting", "backend", cfg.BackendURL, "store", cfg.StorePath)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	wa, err := whatsapp.New(ctx, cfg.StorePath, log)
	if err != nil {
		slog.Error("whatsapp init", "err", err)
		os.Exit(1)
	}

	be := backend.New(cfg.BackendURL, cfg.BridgeAPIKey)
	sttClient := stt.NewWhisperClient(cfg.STTServerURL, 5*time.Second)
	mgr := session.NewManager(be, llm.NewPlaceholder(), sttClient, log)

	// OnIncomingCall MUST be registered before Connect.
	wa.Caller.OnIncomingCall(func(call *meowcaller.Call) {
		go handleIncomingCall(ctx, call, mgr, sttClient, log)
	})

	// Plain message / connection events.
	wa.AddEventHandler(func(evt any) {
		switch v := evt.(type) {
		case *events.Connected:
			slog.Info("session connected", "jid", wa.JID())
		case *events.Disconnected:
			slog.Info("session disconnected")
		case *events.Message:
			slog.Info("message",
				"from", redact(v.Info.Sender.User),
				"text", whatsapp.TextFrom(v),
			)
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

func handleIncomingCall(ctx context.Context, call *meowcaller.Call, mgr *session.Manager, sttSvc stt.STT, log *slog.Logger) {
	peer := call.Peer()
	addedBy := "+" + peer.User
	log.Info("incoming call", "from", redact(peer.User), "call_id", call.ID())

	sess, err := mgr.Start(ctx, call.ID(), addedBy, "whatsapp")
	if err != nil {
		if err == backend.ErrNotAllowed {
			log.Warn("rejecting call — number not on allowlist", "from", redact(peer.User))
			_ = call.Reject()
		} else {
			log.Error("start call", "err", err)
			_ = call.Reject()
		}
		return
	}

	// Open WAV recorder for this call.
	wavPath := wavRecordingPath(call.ID())
	wavSink, err := meowcaller.WAVRecorder(wavPath)
	if err != nil {
		log.Warn("could not open WAV recorder", "path", wavPath, "err", err)
		wavSink = nil
	} else {
		log.Info("recording audio", "path", wavPath)
	}

	// Pipe meowcaller float32 frames into a chan []int16 for the STT layer.
	audioCh := make(chan []int16, 128)
	var closeOnce sync.Once
	closeAudio := func() {
		closeOnce.Do(func() {
			close(audioCh)
			if wavSink != nil {
				if cerr := wavSink.Close(); cerr != nil {
					log.Warn("close WAV", "err", cerr)
				}
			}
		})
	}

	// frameCount tracks how many audio frames arrived — logged at call end for diagnosis.
	var frameCount atomic.Int64

	sink := meowcaller.SinkFunc(func(frame []float32) {
		frameCount.Add(1)
		// Write to WAV file.
		if wavSink != nil {
			_ = wavSink.WriteFrame(frame)
		}
		// Convert to int16 PCM for STT.
		pcm := make([]int16, len(frame))
		for i, s := range frame {
			v := s * 32767
			if v > 32767 {
				v = 32767
			} else if v < -32768 {
				v = -32768
			}
			pcm[i] = int16(v)
		}
		select {
		case audioCh <- pcm:
		case <-ctx.Done():
			closeAudio()
		default: // drop frame rather than block if consumer is slow
		}
	})
	call.Receive(sink)

	// callCtx is cancelled when the call ends or the process shuts down.
	callCtx, cancelCall := context.WithCancel(ctx)

	// Log when RTP media actually starts flowing from the relay.
	call.OnReady(func() {
		log.Info("media ready — RTP flowing", "call_id", call.ID())
		// Heartbeat: log frame count every 5s so we can see audio stop mid-call.
		go func() {
			t := time.NewTicker(5 * time.Second)
			defer t.Stop()
			for {
				select {
				case <-callCtx.Done():
					return
				case <-t.C:
					log.Info("audio heartbeat",
						"call_id", call.ID(),
						"frames_received", frameCount.Load(),
						"audio_ms", frameCount.Load()*int64(meowcaller.FrameSamples)*1000/int64(meowcaller.SampleRate),
					)
				}
			}
		}()
	})

	// Log group call participant changes so we can see the 2-party → group transition.
	call.OnGroupState(func(state meowcaller.GroupCallState) {
		ids := make([]string, 0, len(state.Participants))
		for _, p := range state.Participants {
			ids = append(ids, redact(p.JID.User))
		}
		log.Info("group state update",
			"call_id", call.ID(),
			"transaction", state.TransactionID,
			"participants", ids,
		)
	})

	call.OnEnd(func(reason string) {
		log.Info("call ended",
			"call_id", call.ID(),
			"reason", reason,
			"frames_received", frameCount.Load(),
			"audio_ms", frameCount.Load()*int64(meowcaller.FrameSamples)*1000/int64(meowcaller.SampleRate),
		)
		cancelCall()
		closeAudio()
	})

	if err := call.Answer(); err != nil {
		log.Error("answer call", "err", err)
		cancelCall()
		closeAudio()
		mgr.End(ctx, call.ID())
		return
	}
	log.Info("call answered", "call_id", sess.CallID)

	// Run STT; each final segment is forwarded to the session (which checks the LLM).
	segCh, err := sttSvc.Stream(callCtx, audioCh, meowcaller.SampleRate)
	if err != nil {
		log.Error("stt stream", "err", err)
		cancelCall()
		closeAudio()
		mgr.End(ctx, call.ID())
		return
	}
	for seg := range segCh {
		log.Info("transcript", "call_id", sess.CallID, "text", seg.Text, "start_ms", seg.StartMS, "end_ms", seg.EndMS)
		sess.HandleSegment(ctx, seg)
	}

	// segCh drained (callCtx cancelled) — finalize the call.
	mgr.End(ctx, call.ID())
}

// wavRecordingPath returns the path for a call's WAV recording under recordings/.
func wavRecordingPath(callID string) string {
	ts := time.Now().Format("20060102-150405")
	name := fmt.Sprintf("call_%s_%s.wav", ts, callID)
	if len(name) > 120 {
		name = name[:120] + ".wav"
	}
	return filepath.Join("recordings", name)
}

// redact replaces middle digits of a phone number so it is safe to log.
func redact(phone string) string {
	if len(phone) < 7 {
		return "***"
	}
	return phone[:3] + "****" + phone[len(phone)-3:]
}

