// Package llm defines the language-model interface used for chime-in replies
// and end-of-call summaries. Default implementation: Claude API.
package llm

import "context"

// LLM is the interface the session layer calls.
type LLM interface {
	// ShouldReply checks whether the bot was addressed by triggerName and,
	// if so, returns the reply text. addressed is false when the utterance
	// does not mention the trigger; reply is empty in that case.
	ShouldReply(ctx context.Context, utterance, triggerName string) (reply string, addressed bool, err error)

	// Summarize produces a bullet-point end-of-call summary from the full
	// transcript text.
	Summarize(ctx context.Context, transcript string) (string, error)
}
