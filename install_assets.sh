#!/bin/bash
echo "=== Starting Solaria Offline Asset Installation ==="

# 1. Create target folders
mkdir -p models/vosk
mkdir -p models/piper

# 2. Download and extract Vosk (1GB RAM Optimized Model)
echo "Downloading Vosk Speech-to-Text Model..."
cd models/vosk
wget -q --show-progress https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip -q vosk-model-small-en-us-0.15.zip
rm vosk-model-small-en-us-0.15.zip
cd ../..

# 3. Download and extract Piper (ARM64 Binary)
echo "Downloading Piper ARM64 TTS Engine..."
cd models/piper
wget -q --show-progress https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz
tar -xf piper_linux_aarch64.tar.gz --strip-components=1
rm piper_linux_aarch64.tar.gz

# 4. Download Northern English Male Voice and config
echo "Downloading Northern English Male Voice Model..."
wget -q --show-progress https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx
wget -q --show-progress https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx.json

# Give execution permission to the Piper binary
chmod +x piper

cd ../..
echo "✅ All offline assets installed and ready!"

