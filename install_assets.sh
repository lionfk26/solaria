#!/usr/bin/env bash
#
# install_assets.sh
# Downloads and installs the offline speech models Solaria needs:
#   - Vosk small English STT model
#   - Piper TTS binary (arm64) + a Piper voice (en_GB northern english male)
#
# Safe to re-run; existing extracted assets are skipped.

set -e

BASE_DIR="/home/fred/solaria"
MODELS_DIR="${BASE_DIR}/models"
VOSK_DIR="${MODELS_DIR}/vosk"
PIPER_DIR="${MODELS_DIR}/piper"

VOSK_ZIP_URL="https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
VOSK_ZIP_NAME="vosk-model-small-en-us-0.15.zip"
VOSK_MODEL_DIRNAME="vosk-model-small-en-us-0.15"

PIPER_TAR_URL="https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_arm64.tar.gz"
# NOTE: pinned release tag below per spec (2023.8.15-2). If that tag is
# unavailable on GitHub for your architecture, update PIPER_TAR_URL above.
PIPER_TAR_URL="https://github.com/rhasspy/piper/releases/download/2023.8.15-2/piper_arm64.tar.gz"
PIPER_TAR_NAME="piper_arm64.tar.gz"

VOICE_ONNX_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx"
VOICE_JSON_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx.json"
VOICE_ONNX_NAME="en_GB-northern_english_male-medium.onnx"
VOICE_JSON_NAME="en_GB-northern_english_male-medium.onnx.json"

log() {
    echo -e "[install_assets] $1"
}

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "[install_assets] ERROR: required command '$1' not found. Install it and re-run." >&2
        exit 1
    fi
}

require_cmd wget
require_cmd unzip
require_cmd tar

log "Creating model directories under ${MODELS_DIR} ..."
mkdir -p "${VOSK_DIR}"
mkdir -p "${PIPER_DIR}"

# --- Vosk STT model -----------------------------------------------------
if [ -d "${VOSK_DIR}/${VOSK_MODEL_DIRNAME}" ]; then
    log "Vosk model already present, skipping download."
else
    log "Downloading Vosk small English model..."
    wget -O "/tmp/${VOSK_ZIP_NAME}" "${VOSK_ZIP_URL}"
    log "Extracting Vosk model..."
    unzip -q -o "/tmp/${VOSK_ZIP_NAME}" -d "${VOSK_DIR}"
    rm -f "/tmp/${VOSK_ZIP_NAME}"
    log "Vosk model installed at ${VOSK_DIR}/${VOSK_MODEL_DIRNAME}"
fi

# --- Piper TTS binary -----------------------------------------------------
if [ -x "${PIPER_DIR}/piper/piper" ]; then
    log "Piper binary already present, skipping download."
else
    log "Downloading Piper (arm64) binary release..."
    wget -O "/tmp/${PIPER_TAR_NAME}" "${PIPER_TAR_URL}"
    log "Extracting Piper..."
    tar -xzf "/tmp/${PIPER_TAR_NAME}" -C "${PIPER_DIR}"
    rm -f "/tmp/${PIPER_TAR_NAME}"
    chmod +x "${PIPER_DIR}/piper/piper" || true
    log "Piper binary installed at ${PIPER_DIR}/piper/piper"
fi

# --- Piper voice model -----------------------------------------------------
if [ -f "${PIPER_DIR}/${VOICE_ONNX_NAME}" ] && [ -f "${PIPER_DIR}/${VOICE_JSON_NAME}" ]; then
    log "Piper voice model already present, skipping download."
else
    log "Downloading Piper voice: en_GB-northern_english_male-medium ..."
    wget -O "${PIPER_DIR}/${VOICE_ONNX_NAME}" "${VOICE_ONNX_URL}"
    wget -O "${PIPER_DIR}/${VOICE_JSON_NAME}" "${VOICE_JSON_URL}"
    log "Voice model installed at ${PIPER_DIR}/${VOICE_ONNX_NAME}"
fi

log "All Solaria voice assets installed successfully."
log "Vosk:  ${VOSK_DIR}/${VOSK_MODEL_DIRNAME}"
log "Piper: ${PIPER_DIR}/piper/piper"
log "Voice: ${PIPER_DIR}/${VOICE_ONNX_NAME}"
