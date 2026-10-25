// Package backend is the HTTP client the bridge uses to talk to the Django API.
package backend

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

// Client calls the Django bridge endpoints using the shared secret key.
type Client struct {
	baseURL string
	apiKey  string
	http    *http.Client
}

func New(baseURL, apiKey string) *Client {
	return &Client{
		baseURL: baseURL,
		apiKey:  apiKey,
		http:    &http.Client{Timeout: 10 * time.Second},
	}
}

// StartCallResponse is returned by POST /bridge/calls/.
type StartCallResponse struct {
	ID          string `json:"id"`
	TriggerName string `json:"trigger_name"`
}

// StartCall notifies the backend that the bot was added to a call.
// Returns (nil, ErrNotAllowed) when the backend returns 403 — the bridge must leave.
func (c *Client) StartCall(ctx context.Context, addedBy, platform, externalID string) (*StartCallResponse, error) {
	body := map[string]string{
		"added_by":    addedBy,
		"platform":    platform,
		"external_id": externalID,
	}
	resp, err := c.post(ctx, "/bridge/calls/", body)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusForbidden {
		return nil, ErrNotAllowed
	}
	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("start call: unexpected status %d", resp.StatusCode)
	}
	var out StartCallResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, fmt.Errorf("start call: decode: %w", err)
	}
	return &out, nil
}

// SegmentPayload is one transcript chunk sent to the backend.
type SegmentPayload struct {
	Seq     int    `json:"seq"`
	Speaker string `json:"speaker"`
	Text    string `json:"text"`
	StartMS uint32 `json:"start_ms"`
	EndMS   uint32 `json:"end_ms"`
	IsFinal bool   `json:"is_final"`
}

// PostSegments batch-upserts transcript segments for callID.
func (c *Client) PostSegments(ctx context.Context, callID string, segs []SegmentPayload) error {
	b, err := json.Marshal(segs)
	if err != nil {
		return err
	}
	resp, err := c.postRaw(ctx, "/bridge/calls/"+callID+"/segments/", b)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("post segments: status %d", resp.StatusCode)
	}
	return nil
}

// PostNote posts a note or reply from the bot for callID.
func (c *Client) PostNote(ctx context.Context, callID, kind, text string) error {
	resp, err := c.post(ctx, "/bridge/calls/"+callID+"/notes/", map[string]string{
		"kind": kind,
		"text": text,
	})
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusCreated {
		return fmt.Errorf("post note: status %d", resp.StatusCode)
	}
	return nil
}

// EndCall marks the call as ended and optionally attaches a summary.
func (c *Client) EndCall(ctx context.Context, callID, summary string) error {
	resp, err := c.post(ctx, "/bridge/calls/"+callID+"/end/", map[string]string{
		"summary": summary,
	})
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusNoContent {
		return fmt.Errorf("end call: status %d", resp.StatusCode)
	}
	return nil
}

// ErrNotAllowed is returned by StartCall when the adder is not on the allowlist.
var ErrNotAllowed = fmt.Errorf("caller not on allowlist")

func (c *Client) post(ctx context.Context, path string, body any) (*http.Response, error) {
	b, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}
	return c.postRaw(ctx, path, b)
}

func (c *Client) postRaw(ctx context.Context, path string, body []byte) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+path, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Bridge-Key", c.apiKey)
	return c.http.Do(req)
}
