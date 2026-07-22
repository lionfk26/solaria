#!/usr/bin/env bash
#
# setup.sh
# One-time setup for Solaria. Run this once, right after cloning the repo:
#
#   git clone https://github.com/<you>/solaria.git
#   cd solaria
#   ./setup.sh
#
# It installs system packages, creates the Python virtual environment,
# installs Python dependencies, and downloads the offline Vosk/Piper
# voice models. After it finishes, launch Solaria day-to-day with:
#
#   ./start_solaria.sh

set -e

SOLARIA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SOLARIA_DIR}"

VENV_DIR="${SOLARIA_DIR}/venv"

log() {
    echo -e "\n[setup] $1"
}

# --------------------------------------------------------------------------
# 1. Make scripts executable
# --------------------------------------------------------------------------
log "Setting executable permissions..."
chmod +x start_solaria.sh auto_run.sh install_assets.sh setup.sh 2>/dev/null || true

# --------------------------------------------------------------------------
# 2. System packages (Raspberry Pi OS / Debian-based). Skipped gracefully
#    if apt isn't available, e.g. testing setup.sh on macOS/another distro.
# --------------------------------------------------------------------------
if command -v apt-get >/dev/null 2>&1; then
    log "Installing system packages (python3-venv, unzip, wget, git)..."
    sudo apt-get update -y
    sudo apt-get install -y python3-venv python3-pip unzip wget git alsa-utils
else
    log "apt-get not found, skipping system package install."
    log "Make sure python3-venv, unzip, wget, and git are installed manually."
fi

# --------------------------------------------------------------------------
# 3. Python virtual environment + dependencies
# --------------------------------------------------------------------------
if [ ! -d "${VENV_DIR}" ]; then
    log "Creating Python virtual environment..."
    python3 -m venv "${VENV_DIR}"
else
    log "Virtual environment already exists, reusing it."
fi

log "Installing Python dependencies..."
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip >/dev/null
pip install -r "${SOLARIA_DIR}/requirements.txt"
deactivate

# --------------------------------------------------------------------------
# 4. Offline voice models (Vosk STT + Piper TTS)
# --------------------------------------------------------------------------
log "Downloading voice models (Vosk + Piper)..."
./install_assets.sh

# --------------------------------------------------------------------------
# Done
# --------------------------------------------------------------------------
log "Setup complete."
echo
echo "  Next step: ./start_solaria.sh"
echo "  Default login: admin / solaria2026"
echo
