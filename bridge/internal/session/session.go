// Package session manages the live state of a single active call.
package session

import (
	"context"
	"log/slog"
	"strings"
	"sync"

	"github.com/kimbi619/clippy/bridge/internal/backend"
	"github.com/kimbi619/clippy/bridge/internal/llm"
	"github.com/kimbi619/clippy/bridge/internal/stt"
)

// Session holds everything the bridge needs while a call is active.
type Session struct {
	CallID      string
	TriggerName string

	mu      sync.Mutex
	seq     int
	buf     strings.Builder // rolling transcript for summary
	backend *backend.Client
	llm     llm.LLM
	log     *slog.Logger
}

// Manager creates and tracks active sessions.
type Manager struct {
	backend *backend.Client
	llm     llm.LLM
	stt     stt.STT
	log     *slog.Logger

	mu       sync.Mutex
	sessions map[string]*Session // keyed by whatsapp call ID
}

func NewManager(b *backend.Client, l llm.LLM, s stt.STT, log *slog.Logger) *Manager {
	return &Manager{
		backend:  b,
		llm:      l,
		stt:      s,
		log:      log,
		sessions: make(map[string]*Session),
	}
}

// Start registers a new call with the backend and opens a session.
// Returns (nil, backend.ErrNotAllowed) if the adder is not allowlisted.
func (m *Manager) Start(ctx context.Context, waCallID, addedBy, platform string) (*Session, error) {
	resp, err := m.backend.StartCall(ctx, addedBy, platform, waCallID)
	if err != nil {
		return nil, err
	}
	s := &Session{
		CallID:      resp.ID,
		TriggerName: resp.TriggerName,
		backend:     m.backend,
		llm:         m.llm,
		log:         m.log,
	}
	m.mu.Lock()
	m.sessions[waCallID] = s
	m.mu.Unlock()
	m.log.Info("call started", "call_id", s.CallID, "trigger", s.TriggerName, "added_by", redact(addedBy))
	return s, nil
}

// Get returns the active session for a whatsapp call ID, or nil.
func (m *Manager) Get(waCallID string) *Session {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.sessions[waCallID]
}

// End closes the session and notifies the backend.
func (m *Manager) End(ctx context.Context, waCallID string) {
	m.mu.Lock()
	s, ok := m.sessions[waCallID]
	delete(m.sessions, waCallID)
	m.mu.Unlock()
	if !ok {
		return
	}
	summary, _ := m.llm.Summarize(ctx, s.buf.String())
	if err := m.backend.EndCall(ctx, s.CallID, summary); err != nil {
		m.log.Error("end call", "err", err)
	}
	m.log.Info("call ended", "call_id", s.CallID)
}

// HandleSegment pushes a transcript segment to the backend and checks whether
// the bot should reply.
func (s *Session) HandleSegment(ctx context.Context, seg stt.Segment) {
	s.mu.Lock()
	s.seq++
	seq := s.seq
	if seg.IsFinal {
		s.buf.WriteString(seg.Text + " ")
	}
	s.mu.Unlock()

	payload := []backend.SegmentPayload{{
		Seq:     seq,
		Speaker: seg.Speaker,
		Text:    seg.Text,
		StartMS: seg.StartMS,
		EndMS:   seg.EndMS,
		IsFinal: seg.IsFinal,
	}}
	if err := s.backend.PostSegments(ctx, s.CallID, payload); err != nil {
		s.log.Error("post segment", "err", err)
	}

	if !seg.IsFinal {
		return
	}
	reply, addressed, err := s.llm.ShouldReply(ctx, seg.Text, s.TriggerName)
	if err != nil {
		s.log.Error("llm", "err", err)
		return
	}
	if addressed {
		if err := s.backend.PostNote(ctx, s.CallID, "reply", reply); err != nil {
			s.log.Error("post note", "err", err)
		}
		s.log.Info("bot replied", "call_id", s.CallID, "reply", reply)
	}
}

func redact(phone string) string {
	if len(phone) < 7 {
		return "***"
	}
	return phone[:3] + "****" + phone[len(phone)-3:]
}
