#!/bin/bash
set -e

echo "================================================="
echo "   DOWNLOADING SOLARIA LOCAL AI ENGINES          "
echo "================================================="

mkdir -p /home/fred/solaria/models/vosk
mkdir -p /home/fred/solaria/models/piper

# 1. Download Vosk STT Model
echo "--> Downloading Vosk STT Model..."
cd /home/fred/solaria/models/vosk
wget -q --show-progress https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip -q vosk-model-small-en-us-0.15.zip
rm vosk-model-small-en-us-0.15.zip

# 2. Download Piper TTS Executable (ARM64)
echo "--> Downloading Piper TTS Engine..."
cd /home/fred/solaria/models/piper
wget -q --show-progress https://github.com/rhasspy/piper/releases/download/2023.8.15-2/piper_arm64.tar.gz
tar -xzf piper_arm64.tar.gz --strip-components=1
rm piper_arm64.tar.gz
chmod +x piper

# 3. Download Northern English Voice Model
echo "--> Downloading Voice Model..."
wget -q --show-progress https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx
wget -q --show-progress https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx.json

echo "✅ AI Engines downloaded and placed successfully!"
