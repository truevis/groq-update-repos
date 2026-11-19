# Kokoro-FastAPI on alpha (no Docker)

Run on alpha:
- Linux/macOS: `./install.sh` (Linux: `./install.sh --service` to run via systemd)
- Windows: `powershell -ExecutionPolicy Bypass -File install.ps1`
- Then, in another terminal: `./test.sh`

Endpoint: `http://localhost:8880/v1/audio/speech` (OpenAI-compatible), docs at `/docs`, UI at `/web`.
Other machines: `http://alpha:8880` (open port 8880; no auth, keep off the internet).

Scripts are unverified on alpha. If a step fails, check the upstream README:
https://github.com/remsky/Kokoro-FastAPI
