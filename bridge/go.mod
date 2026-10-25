module github.com/kimbi619/clippy/bridge

go 1.23

require (
	github.com/mdp/qrterminal/v3 v3.2.0
	github.com/purpshell/meowcaller v0.0.0-20260726180203-6d9b7b2c1807
	go.mau.fi/whatsmeow v0.0.0-20260722203353-e9a033b24933
	google.golang.org/protobuf v1.36.11
	modernc.org/sqlite v1.37.1
)

// Run `go mod tidy` after checkout to pull indirect deps and generate go.sum.
