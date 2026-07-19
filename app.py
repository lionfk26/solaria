from flask import Flask, request, jsonify
import curses
import threading
import json
import os
import time
import socket
import subprocess
from datetime import datetime
from collections import Counter
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
MNT_TARGET = "/media/pi/RPI-RP2"  # Default mount path for Raspberry Pi OS Bookworm

# Local AI Paths
VOSK_MODEL_PATH = "models/vosk/vosk-model-small-en-us-0.15"
PIPER_EXEC = "models/piper/piper"
PIPER_MODEL = "models/piper/en_GB-northern_english_male-medium.onnx"

# --- MENU DATABASE LOADING ---
MENU_FILE = "menu.json"
menu_items = []

if os.path.exists(MENU_FILE):
    try:
        with open(MENU_FILE, "r") as mf:
            menu_data = json.load(mf)
            for menu_type, categories in menu_data.get("menus", {}).items():
                for category, items in categories.items():
                    for item in items:
                        menu_items.append({
                            "name": item["name"],
                            "clean_name": item["name"].lower().replace("&", "and").replace("-", " "),
                            "price": item.get("price") or item.get("base_price", 0.0)
                        })
        # Sort long names first to maximize phrase matching accuracy
        menu_items.sort(key=lambda x: len(x["clean_name"]), reverse=True)
    except Exception:
        pass

# Initialize Vosk Model
if os.path.exists(VOSK_MODEL_PATH):
    try:
        speech_model = Model(VOSK_MODEL_PATH)
        ai_log = "AI Engine Ready (Vosk TCP Stream Active & Piper Northern Male Connected)"
    except Exception as e:
        speech_model = None
        ai_log = f"Vosk Init Error: {str(e)}"
else:
    speech_model = None
    ai_log = f"Error: Vosk model missing at {VOSK_MODEL_PATH}"

def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def flash_connected_pico() -> None:
    """Background monitor thread that automatically configures and flashes connected Pico 2W boards."""
    global flash_log
    while True:
        if os.path.exists(MNT_TARGET):
            flash_log = "⚡ Pico 2W Mass Storage detected! Compiling dynamic firmware..."
            time.sleep(1)
            
            local_ip = get_local_ip()
            wifi_ssid = "Your_Restaurant_WiFi"
            wifi_pass = "Your_WiFi_Password"
            
            # Safe parsing from config if available
            if os.path.exists("wifi_config.json"):
                try:
                    with open("wifi_config.json", "r") as wf:
                        wconf = json.load(wf)
                        wifi_ssid = wconf.get("ssid", wifi_ssid)
                        wifi_pass = wconf.get("password", wifi_pass)
                except Exception:
                    pass

            try:
                # 1. Read templates
                with open(os.path.join(PICO_TEMPLATE_DIR, "boot.py"), "r") as f:
                    boot_code = f.read()
                with open(os.path.join(PICO_TEMPLATE_DIR, "main.py"), "r") as f:
                    main_code = f.read()

                # 2. Inject environment configurations
                boot_code = boot_code.replace('WIFI_SSID = "Your_Restaurant_WiFi"', f'WIFI_SSID = "{wifi_ssid}"')
                boot_code = boot_code.replace('WIFI_PASSWORD = "Your_WiFi_Password"', f'WIFI_PASSWORD = "{wifi_pass}"')
                main_code = main_code.replace('SERVER_IP = "<SERVER_IP>"', f'SERVER_IP = "{local_ip}"')

                # Assign automatic table identifier based on existing pool
                with data_lock:
                    next_id = len(tables_status) + 1
                assigned_id = f"Table_{next_id}"
                main_code = main_code.replace('TABLE_ID = "Table_1"', f'TABLE_ID = "{assigned_id}"')

                # 3. Write compiled scripts to active mass storage
                with open(os.path.join(MNT_TARGET, "boot.py"), "w") as f:
                    f.write(boot_code)
                with open(os.path.join(MNT_TARGET, "main.py"), "w") as f:
                    f.write(main_code)

                flash_log = f"✅ Flashing Complete! Disconnected board provisioned safely as: {assigned_id}"
                
                # Force Linux filesystem sync and unmount
                subprocess.run(f"sync {MNT_TARGET}", shell=True)
            except Exception as e:
                flash_log = f"❌ Error flashing Pico 2W: {str(e)}"
            
            # Cooldown to allow safe detachment of the device
            time.sleep(5)
        else:
            flash_log = "Awaiting Pico 2W connections... (Hold BOOTSEL while inserting USB)"
            time.sleep(2)

def update_terminal(stdscr) -> None:
    """Curses terminal visualization engine mapping live threads and tables status."""
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(500)
    
    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        
        # Border decorations
        stdscr.attron(curses.A_BOLD)
        stdscr.addstr(0, 2, " SOLARIA TERMINAL DASHBOARD - ACTIVE - PI 5 POWERED ")
        stdscr.attroff(curses.A_BOLD)
        stdscr.addstr(0, w - 25, f"Clock: {datetime.now().strftime('%H:%M:%S')}")
        
        # Draw Panels
        stdscr.addstr(2, 2, "==================== SYSTEM & HARDWARE LINK ====================")
        stdscr.addstr(3, 2, f"[STATUS]     Server IP: {get_local_ip()} | Listening Ports: 5000 (HTTP) & 5001 (TCP)")
        stdscr.addstr(4, 2, f"[AUTO-FLASH] {flash_log}")
        stdscr.addstr(5, 2, f"[AI ENGINES] {ai_log}")
        stdscr.addstr(6, 2, "================================================================")
        
        stdscr.addstr(8, 2, "========================= ACTIVE TABLES ========================")
        
        row = 10
        with data_lock:
            if not tables_status:
                stdscr.addstr(row, 4, "No active table endpoints discovered on the network yet.", curses.A_DIM)
            else:
                for tid, info in tables_status.items():
                    if row + 4 >= h:
                        break
                    
                    status_str = f"[{tid}] -> Status: {info['status']}"
                    
                    if info['assistance']:
                        stdscr.addstr(row, 4, f"{status_str} | ⚠️  REQUESTING MANAGER ASSISTANCE", curses.A_STANDOUT | curses.A_BLINK)
                    else:
                        stdscr.addstr(row, 4, status_str)
                    
                    orders_list = ", ".join(info['orders']) if info['orders'] else "None"
                    stdscr.addstr(row+1, 6, f"Current Orders: {orders_list}", curses.A_DIM)
                    row += 3
                    
        stdscr.refresh()
        
        try:
            key = stdscr.getch()
            if key == ord('q'):
                break
        except Exception:
            pass

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

# --- LIVE AUDIO TCP STREAM SERVER LOGIC ---
def handle_live_audio(client_socket: socket.socket, addr: Any) -> None:
    """Manages a dedicated stream channel tracking audio payloads from a precise table socket."""
    table_id = "Unknown"
    try:
        # Read the initial header containing the padded 10-byte Table identifier
        table_id_raw = client_socket.recv(10).decode('utf-8', errors='ignore').strip()
        if table_id_raw.startswith("Table"):
            table_id = table_id_raw
            with data_lock:
                if table_id in tables_status:
                    tables_status[table_id]['status'] = "🔴 LIVE STREAMING"

        if not speech_model:
            client_socket.close()
            return
            
        rec = KaldiRecognizer(speech_model, 16000)
        
        # Read streaming data directly into the active Kaldi waveform pipeline
        while True:
            data = client_socket.recv(4096)
            if not data:
                break
            rec.AcceptWaveform(data)

        # Process speech matching parameters upon completion of audio ingestion
        result = json.loads(rec.FinalResult())
        spoken_text = result.get("text", "").lower().replace("and", " ").replace("please", "")
        
        reply_text = "I didn't quite catch that, mate. Could you say it again?"
        matched_items = []

        if any(word in spoken_text for word in ["help", "manager", "assistance", "staff"]):
            with data_lock:
                if table_id in tables_status:
                    tables_status[table_id]['assistance'] = True
            reply_text = "No worries, I've logged your request and called a manager over to your table."
        else:
            remaining_text = spoken_text
            for item in menu_items:
                if item["clean_name"] in remaining_text:
                    matched_items.append(item)
                    remaining_text = remaining_text.replace(item["clean_name"], "")
                    
            if matched_items:
                with data_lock:
                    if table_id in tables_status:
                        for item in matched_items:
                            tables_status[table_id]['orders'].append(f"{item['name']} (£{item['price']:.2f})")
                
                item_counts = Counter([i['name'] for i in matched_items])
                spoken_list = [f"{count} orders of {name}" if count > 1 else name for name, count in item_counts.items()]
                
                if len(spoken_list) == 1:
                    formatted_items = spoken_list[0]
                elif len(spoken_list) == 2:
                    formatted_items = f"{spoken_list[0]} and {spoken_list[1]}"
                else:
                    formatted_items = ", ".join(spoken_list[:-1]) + ", and " + spoken_list[-1]
                    
                reply_text = f"Got it! I have added {formatted_items} to your table's order."

        # Compile TTS response directly to raw output blocks
        out_file = f"/tmp/response_{table_id}.raw"
        subprocess.run(f"echo '{reply_text}' | {PIPER_EXEC} --model {PIPER_MODEL} --output_raw > {out_file}", shell=True)
        
        with open(out_file, "rb") as f:
            client_socket.sendall(f.read())
            
    except Exception:
        pass
    finally:
        with data_lock:
            if table_id in tables_status and tables_status[table_id]['status'] == "🔴 LIVE STREAMING":
                tables_status[table_id]['status'] = "Online"
        client_socket.close()

def run_tcp_server() -> None:
    """Dedicated parallel listening server bound to Port 5001 handling live data traffic streams."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', 5001))
    server.listen(15)
    
    while True:
        try:
            client_sock, addr = server.accept()
            threading.Thread(target=handle_live_audio, args=(client_sock, addr), daemon=True).start()
        except Exception:
            time.sleep(1)

def run_flask() -> None:
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=run_tcp_server, daemon=True).start()
    threading.Thread(target=flash_connected_pico, daemon=True).start()
    
    curses.wrapper(update_terminal)