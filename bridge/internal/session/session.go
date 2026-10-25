// Package session manages the live state of a single call.
package session

// Session holds everything the bridge needs while a call is active.
type Session struct {
	CallID      string // UUID assigned by the Django backend
	TriggerName string // e.g. "Clippy" — the name participants use to address the bot
}
