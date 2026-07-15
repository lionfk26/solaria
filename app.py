from flask import Flask, request, jsonify, send_file
import curses
import threading
import json
import os
import shutil
import time
import subprocess
from datetime import datetime
from typing import Dict, Any
from vosk import Model, KaldiRecognizer

app = Flask(__name__)

# Core state and thread synchronization
data_lock = threading.Lock()
tables_status: Dict[str, Dict[str, Any]] = {}
flash_log = "No board connected yet."
ai_log = "AI Engine Initializing..."

# Configuration paths for USB auto-flashing and AI
PICO_TEMPLATE_DIR = os.path.expanduser("~/solaria/pico_template")
MNT_TARGET = "/media/pi/RPI-RP2"  # Default mount path for Raspberry Pi OS

# Local AI Paths
VOSK_MODEL_PATH = "models/vosk/vosk-model-small-en-us-0.15"
PIPER_EXEC = "models/piper/piper"
PIPER_MODEL = "models/piper/en_GB-northern_english_male-medium.onnx"

# Initialize Local Speech Recognition
if os.path.exists(VOSK_MODEL_PATH):
    try:
        speech_model = Model(VOSK_MODEL_PATH)
        ai_log = "AI Engine Ready (Vosk & Northern Male Active)"
    except Exception as e:
        speech_model = None
        ai_log = f"Vosk Error: {str(e)}"
else:
    speech_model = None
    ai_log = "Warning: Vosk model folder not found in models/vosk/"

def flash_connected_pico() -> None:
    """Monitors USB subsystem for raw Pico 2W boards and flashes them sequentially."""
    global flash_log
    while True:
        if os.path.exists(MNT_TARGET):
            flash_log = "⚡ Pico detected! Injecting custom profile..."
            try:
                # 1. Determine next table ID sequentially
                with data_lock:
                    next_num = len(tables_status) + 1
                    assigned_id = f"Table_{next_num}"
                
                # Fetch Wi-Fi settings dynamically
                ssid, pwd = "Your_Restaurant_WiFi", "Your_WiFi_Password"
                if os.path.exists("wifi_config.json"):
                    with open("wifi_config.json", "r") as wf:
                        wifi_data = json.load(wf)
                        ssid = wifi_data.get("ssid", ssid)
                        pwd = wifi_data.get("password", pwd)

                # Edit and write boot.py
                with open(os.path.join(PICO_TEMPLATE_DIR, "boot.py"), "r") as f:
                    boot_code = f.read()
                boot_code = boot_code.replace('WIFI_SSID = "Your_Restaurant_WiFi"', f'WIFI_SSID = "{ssid}"')
                boot_code = boot_code.replace('WIFI_PASSWORD = "Your_WiFi_Password"', f'WIFI_PASSWORD = "{pwd}"')
                
                with open(os.path.join(MNT_TARGET, "boot.py"), "w") as f:
                    f.write(boot_code)
                
                # Edit and write main.py
                with open(os.path.join(PICO_TEMPLATE_DIR, "main.py"), "r") as f:
                    main_code = f.read()
                modified_code = main_code.replace('TABLE_ID = "Table_1"', f'TABLE_ID = "{assigned_id}"')
                
                with open(os.path.join(MNT_TARGET, "main.py"), "w") as f:
                    f.write(modified_code)
                
                flash_log = f"✅ Flashed successfully as {assigned_id}! Safe to unplug."
                
                with data_lock:
                    tables_status[assigned_id] = {"status": "Flashed / Offline", "assistance": False, "orders": []}
                
                # Cooldown to avoid double flashing
                time.sleep(10)
            except Exception as e:
                flash_log = f"❌ Flash failure: {str(e)}"
        else:
            flash_log = "🔌 Awaiting Pico 2W (Hold BOOTSEL button while plugging USB)..."
            
        time.sleep(2)

def update_terminal(stdscr) -> None:
    curses.curs_set(0)
    stdscr.clear()

    while True:
        stdscr.erase()
        stdscr.addstr(0, 0, "==========================================================", curses.A_BOLD)
        stdscr.addstr(1, 0, "                SOLARIA TERMINAL DASHBOARD                ", curses.A_BOLD)
        stdscr.addstr(2, 0, f" Status: Active | Clock: {datetime.now().strftime('%H:%M:%S')}")
        stdscr.addstr(3, 0, "==========================================================", curses.A_BOLD)
        
        stdscr.addstr(5, 0, "--- System & Hardware Link ---", curses.A_UNDERLINE)
        stdscr.addstr(6, 2, flash_log)
        stdscr.addstr(7, 2, f"AI Status: {ai_log}")
        stdscr.addstr(8, 0, "-----------------------------")

        row = 10
        with data_lock:
            if not tables_status:
                stdscr.addstr(row, 2, "Waiting for endpoints to check-in over network...", curses.A_BLINK)
            else:
                for table_id, info in tables_status.items():
                    status = info.get('status', 'Offline')
                    help_str = "⚠️  NEEDS HELP" if info.get('assistance') else "Clear"
                    orders = ", ".join(info.get('orders', [])) or "None"
                    
                    attr = curses.A_REVERSE if info.get('assistance') else curses.A_NORMAL
                    
                    stdscr.addstr(row, 2, f"[{table_id}]", curses.A_BOLD | attr)
                    stdscr.addstr(row, 18, f"Status: {status}")
                    stdscr.addstr(row, 38, f"Assistance: {help_str}", attr)
                    stdscr.addstr(row + 1, 4, f"Orders: {orders}")
                    row += 3
        
        stdscr.refresh()
        time.sleep(0.5)

# --- REST & AI API ENDPOINTS ---
@app.route('/register_table', methods=['POST'])
def register() -> Any:
    data = request.json or {}
    table_id = data.get('table_id')
    if table_id:
        with data_lock:
            if table_id not in tables_status:
                tables_status[table_id] = {"status": "Online", "assistance": False, "orders": []}
            else:
                tables_status[table_id]['status'] = "Online"
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error"}), 400

@app.route('/voice_command', methods=['POST'])
def handle_voice():
    """Receives 16kHz PCM audio from table unit, transcribes it, and responds with 22.05kHz Piper voice."""
    table_id = request.headers.get('Table-ID', 'Unknown')
    raw_audio = request.data  # Raw 16-bit 16000Hz PCM
    
    if not speech_model:
        return "Speech Model Offline", 500

    # 1. Transcribe audio with Vosk
    rec = KaldiRecognizer(speech_model, 16000)
    rec.AcceptWaveform(raw_audio)
    result = json.loads(rec.Result())
    spoken_text = result.get("text", "")
    
    # 2. Local natural-language checking
    reply_text = "I didn't quite catch that, mate. Could you say it again?"
    if "help" in spoken_text or "manager" in spoken_text:
        with data_lock:
            if table_id in tables_status:
                tables_status[table_id]['assistance'] = True
        reply_text = "No worries, I've called a manager over to your table."
    elif "water" in spoken_text:
        reply_text = "Alright, I'll send someone over with some water for you."
        with data_lock:
            if table_id in tables_status:
                tables_status[table_id]['orders'].append("Water")

    # 3. Generate Speech output with Piper (outputs raw mono PCM directly)
    out_file = f"/tmp/response_{table_id}.raw"
    # Execute the ARM64 binary with the Northern English voice model
    piper_cmd = f"echo '{reply_text}' | {PIPER_EXEC} --model {PIPER_MODEL} --output_raw > {out_file}"
    subprocess.run(piper_cmd, shell=True)

    return send_file(out_file, mimetype="application/octet-stream")

def run_flask():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)  # Prevent terminal pollution
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    api_thread = threading.Thread(target=run_flask, daemon=True)
    api_thread.start()
    
    flasher_thread = threading.Thread(target=flash_connected_pico, daemon=True)
    flasher_thread.start()
    
    curses.wrapper(update_terminal)
