#!/usr/bin/env bash
# Installs Kokoro-FastAPI natively (no Docker) on Linux or macOS.
# Usage: ./install.sh [--service]   (--service = install systemd unit on Linux)
set -euo pipefail

INSTALL_DIR="${KOKORO_DIR:-$HOME/Kokoro-FastAPI}"
REPO="https://github.com/remsky/Kokoro-FastAPI.git"
OS="$(uname -s)"

echo "==> Installing system dependencies ($OS)"
if [ "$OS" = "Darwin" ]; then
  command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
  brew install espeak-ng git uv
elif [ "$OS" = "Linux" ]; then
  if command -v apt-get >/dev/null; then
    sudo apt-get update && sudo apt-get install -y espeak-ng git curl
  elif command -v dnf >/dev/null; then
    sudo dnf install -y espeak-ng git curl
  elif command -v pacman >/dev/null; then
    sudo pacman -S --needed --noconfirm espeak-ng git curl
  else
    echo "Unknown package manager; install espeak-ng, git, curl manually."; exit 1
  fi
  command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; }
else
  echo "Unsupported OS: $OS (use install.ps1 on Windows)"; exit 1
fi

echo "==> Cloning repo to $INSTALL_DIR"
if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" pull --ff-only
else
  git clone "$REPO" "$INSTALL_DIR"
fi

# Pick GPU vs CPU start script
if [ "$OS" = "Linux" ] && command -v nvidia-smi >/dev/null && nvidia-smi >/dev/null 2>&1; then
  START="start-gpu.sh"
else
  START="start-cpu.sh"
fi
echo "==> Using $START"
chmod +x "$INSTALL_DIR"/start-*.sh

if [ "${1:-}" = "--service" ] && [ "$OS" = "Linux" ]; then
  sudo tee /etc/systemd/system/kokoro.service >/dev/null <<UNIT
[Unit]
Description=Kokoro TTS (FastAPI)
After=network.target

[Service]
User=$USER
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$INSTALL_DIR/$START
Restart=always

[Install]
WantedBy=multi-user.target
UNIT
  sudo systemctl daemon-reload
  sudo systemctl enable --now kokoro
  echo "==> Service started: systemctl status kokoro"
else
  echo "==> Starting server in foreground (Ctrl+C to stop). First run downloads the model."
  cd "$INSTALL_DIR" && exec "./$START"
fi
