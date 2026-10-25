package config

import (
	"os"
	"testing"
)

func TestLoad_MissingKey(t *testing.T) {
	os.Unsetenv("BRIDGE_API_KEY")
	_, err := Load()
	if err == nil {
		t.Fatal("expected error when BRIDGE_API_KEY is empty")
	}
}

func TestLoad_AllowedNumbers(t *testing.T) {
	t.Setenv("BRIDGE_API_KEY", "secret")
	t.Setenv("ALLOWED_NUMBERS", "+237600000001, +237600000002 , ")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(cfg.AllowedNumbers) != 2 {
		t.Fatalf("want 2 numbers, got %d", len(cfg.AllowedNumbers))
	}
}

func TestLoad_Defaults(t *testing.T) {
	t.Setenv("BRIDGE_API_KEY", "secret")
	os.Unsetenv("BACKEND_URL")
	os.Unsetenv("LOG_LEVEL")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.BackendURL != "http://localhost:8000" {
		t.Errorf("unexpected default BackendURL: %s", cfg.BackendURL)
	}
	if cfg.LogLevel != "info" {
		t.Errorf("unexpected default LogLevel: %s", cfg.LogLevel)
	}
}
