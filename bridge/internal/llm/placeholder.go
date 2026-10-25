package llm

import (
	"context"
	"strings"
)

// Placeholder is a no-cost LLM implementation used while the real model
// integration (Ollama / Claude) is not yet configured. It replies with a
// fixed message when addressed and produces a stub summary.
type Placeholder struct{}

func NewPlaceholder() *Placeholder { return &Placeholder{} }

func (p *Placeholder) ShouldReply(_ context.Context, utterance, triggerName string) (string, bool, error) {
	if triggerName == "" {
		triggerName = "clippy"
	}
	if !strings.Contains(strings.ToLower(utterance), strings.ToLower(triggerName)) {
		return "", false, nil
	}
	reply := "Hey! I'm Clippy, your AI call assistant. I'm listening and taking notes. " +
		"(AI responses will be available once a language model is connected.)"
	return reply, true, nil
}

func (p *Placeholder) Summarize(_ context.Context, _ string) (string, error) {
	return "Call summary not yet available — language model integration pending.", nil
}
