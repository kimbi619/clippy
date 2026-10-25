package config

import (
	"fmt"
	"os"
	"strings"
)

type Config struct {
	BackendURL     string   // Django backend base URL
	BridgeAPIKey   string   // shared secret sent as X-Bridge-Key
	WhatsAppPhone  string   // E.164 number the bot is registered on
	StorePath      string   // path to the whatsmeow SQLite session file
	AllowedNumbers []string // E.164 numbers allowed to add the bot
	AssemblyAIKey  string
	AnthropicKey   string
	LogLevel       string // debug | info | warn | error
}

func Load() (*Config, error) {
	c := &Config{
		BackendURL:    env("BACKEND_URL", "http://localhost:8000"),
		BridgeAPIKey:  os.Getenv("BRIDGE_API_KEY"),
		WhatsAppPhone: os.Getenv("WHATSAPP_PHONE"),
		StorePath:     env("STORE_PATH", "whatsmeow.db"),
		AssemblyAIKey: os.Getenv("ASSEMBLYAI_KEY"),
		AnthropicKey:  os.Getenv("ANTHROPIC_KEY"),
		LogLevel:      env("LOG_LEVEL", "info"),
	}

	if raw := os.Getenv("ALLOWED_NUMBERS"); raw != "" {
		for _, n := range strings.Split(raw, ",") {
			if n = strings.TrimSpace(n); n != "" {
				c.AllowedNumbers = append(c.AllowedNumbers, n)
			}
		}
	}

	if c.BridgeAPIKey == "" {
		return nil, fmt.Errorf("BRIDGE_API_KEY is required")
	}

	return c, nil
}

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
