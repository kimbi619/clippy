# dev.ps1 — common bridge dev tasks. Run from the repo root.
# Usage: .\scripts\dev.ps1 <command>
#   vet    run go vet
#   test   run go test
#   build  compile the binary
#   run    build and run (requires .env in bridge/)

param (
    [Parameter(Mandatory = $true)]
    [ValidateSet("vet", "test", "build", "run")]
    [string]$Command
)

Set-Location "$PSScriptRoot\..\bridge"

switch ($Command) {
    "vet"   { go vet ./... }
    "test"  { go test ./... }
    "build" { go build -o clippy.exe ./cmd/clippy }
    "run" {
        if (Test-Path ".env") {
            Get-Content ".env" | ForEach-Object {
                if ($_ -match "^\s*([^#][^=]+)=(.*)$") {
                    [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
                }
            }
        }
        go run ./cmd/clippy
    }
}
