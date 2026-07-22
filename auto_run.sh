#!/usr/bin/env bash
#
# auto_run.sh
# Called by start_solaria.sh after a successful login. Validates
# connectivity, updates the codebase, prepares the venv, and launches
# the main Solaria application.

set -e

SOLARIA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SOLARIA_DIR}"

VENV_DIR="${SOLARIA_DIR}/venv"

echo "[auto_run] Checking internet connectivity..."
if ping -c 1 -W 3 8.8.8.8 >/dev/null 2>&1; then
    ONLINE=1
    echo "[auto_run] Internet connection OK."
else
    ONLINE=0
    echo "[auto_run] WARNING: no internet connection detected. Skipping git update."
fi

if [ "${ONLINE}" -eq 1 ] && [ -d "${SOLARIA_DIR}/.git" ]; then
    echo "[auto_run] Fetching latest changes..."
    git fetch origin || echo "[auto_run] WARNING: git fetch failed, continuing with local copy."
    echo "[auto_run] Pulling origin/main..."
    git pull origin main || echo "[auto_run] WARNING: git pull failed, continuing with local copy."
else
    echo "[auto_run] Skipping git sync (offline or not a git repo)."
fi

if [ ! -d "${VENV_DIR}" ]; then
    echo "[auto_run] Creating virtual environment..."
    python3 -m venv "${VENV_DIR}"
fi

echo "[auto_run] Activating virtual environment..."
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

echo "[auto_run] Installing/updating Python dependencies..."
pip install --upgrade pip >/dev/null
pip install -r "${SOLARIA_DIR}/requirements.txt"

echo "[auto_run] Launching Solaria..."
exec python3 "${SOLARIA_DIR}/app.py"
