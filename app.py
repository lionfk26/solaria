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

# Configuration paths for Pi Lite USB auto-flashing and AI
PICO_TEMPLATE_DIR = "/home/fred/solaria/pico_template"
MNT_TARGET = "/media/fred/RPI-RP2"  # Targets user 'fred' USB auto-mount

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
        menu_items.sort(key=lambda x: len(x["clean_name"]), reverse=True)
    except Exception:
        pass

# --- AI ENGINE INITIALIZATION ---
if os.path.exists(VOSK_MODEL_PATH):
    try:
        speech_model = Model(VOSK_MODEL_PATH)
        ai_log = "AI Engine Ready (Vosk TCP & Piper Active)"
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
    global flash_log
    while True:
        if os.path.exists(MNT_TARGET):
            flash_log = "⚡ Pico 2W detected! Compiling firmware..."
            time.sleep(1)
            
            local_ip = get_local_ip()
            wifi_ssid, wifi_pass = "Your_Restaurant_WiFi", "Your_WiFi_Password"
            
            if os.path.exists("wifi_config.json"):
                try:
                    with open("wifi_config.json", "r") as wf:
                        wconf = json.load(wf)
                        wifi_ssid, wifi_pass = wconf.get("ssid", wifi_ssid), wconf.get("password", wifi_pass)
                except Exception:
                    pass

            try:
                with open(os.path.join(PICO_TEMPLATE_DIR, "boot.py"), "r") as f:
                    boot_code = f.read()
                with open(os.path.join(PICO_TEMPLATE_DIR, "main.py"), "r") as f:
                    main_code = f.read()

                boot_code = boot_code.replace('WIFI_SSID = "Your_Restaurant_WiFi"', f'WIFI_SSID = "{wifi_ssid}"')
                boot_code = boot_code.replace('WIFI_PASSWORD = "Your_WiFi_Password"', f'WIFI_PASSWORD = "{wifi_pass}"')
                main_code = main_code.replace('SERVER_IP = "<SERVER_IP>"', f'SERVER_IP = "{local_ip}"')

                with data_lock:
                    next_id = len(tables_status) + 1
                assigned_id = f"Table_{next_id}"
                main_code = main_code.replace('TABLE_ID = "Table_1"', f'TABLE_ID = "{assigned_id}"')

                with open(os.path.join(MNT_TARGET, "boot.py"), "w") as f:
                    f.write(boot_code)
                with open(os.path.join(MNT_TARGET, "main.py"), "w") as f:
                    f.write(main_code)

                flash_log = f"✅ Flashed successfully: {assigned_id}"
                subprocess.run(["sync"], timeout=10)
            except Exception as e:
                flash_log = f"❌ Error flashing: {str(e)}"
            
            time.sleep(5)
        else:
            flash_log = "Awaiting Pico 2W connections..."
            time.sleep(2)

def update_terminal(stdscr) -> None:
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(500)
    
    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        
        stdscr.attron(curses.A_BOLD)
        stdscr.addstr(0, 2, " SOLARIA TERMINAL DASHBOARD - ACTIVE - PI LITE SYSTEM ")
        stdscr.attroff(curses.A_BOLD)
        stdscr.addstr(0, w - 25, f"Clock: {datetime.now().strftime('%H:%M:%S')}")
        
        stdscr.addstr(2, 2, "==================== SYSTEM & HARDWARE LINK ====================")
        stdscr.addstr(3, 2, f"[STATUS]     Server IP: {get_local_ip()} | Listening Ports: 5000 & 5001")
        stdscr.addstr(4, 2, f"[AUTO-FLASH] {flash_log}")
        stdscr.addstr(5, 2, f"[AI ENGINES] {ai_log}")
        stdscr.addstr(6, 2, "================================================================")
        stdscr.addstr(8, 2, "========================= ACTIVE TABLES ========================")
        
        row = 10
        with data_lock:
            if not tables_status:
                stdscr.addstr(row, 4, "No active table endpoints discovered.", curses.A_DIM)
            else:
                for tid, info in tables_status.items():
                    if row + 4 >= h: break 
                    
                    status_str = f"[{tid}] -> Status: {info['status']}"
                    
                    if info['assistance']:
                        stdscr.addstr(row, 4, f"{status_str} | ⚠️ NEEDS MANAGER", curses.A_STANDOUT | curses.A_BLINK)
                    else:
                        stdscr.addstr(row, 4, status_str)
                    
                    orders_list = ", ".join(info['orders']) if info['orders'] else "None"
                    pending_list = ", ".join(info.get('pending_orders', [])) if info.get('pending_orders') else "None"
                    
                    stdscr.addstr(row+1, 6, f"Confirmed Orders: {orders_list}", curses.A_DIM)
                    stdscr.addstr(row+2, 6, f"Pending Confirmation: {pending_list}", curses.color_pair(3) if curses.has_colors() else curses.A_DIM)
                    
                    row += 4
                    
        stdscr.refresh()
        try:
            if stdscr.getch() == ord('q'): break
        except Exception:
            pass

@app.route('/register_table', methods=['POST'])
def register() -> Any:
    data = request.json or {}
    table_id = data.get('table_id')
    if table_id:
        with data_lock:
            if table_id not in tables_status:
                tables_status[table_id] = {"status": "Online", "assistance": False, "orders": [], "pending_orders": []}
            else:
                tables_status[table_id]['status'] = "Online"
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error"}), 400

def handle_live_audio(client_socket: socket.socket, addr: Any) -> None:
    table_id = "Unknown"
    client_socket.settimeout(30.0)
    try:
        table_id_raw = client_socket.recv(10).decode('utf-8', errors='ignore').strip()
        if table_id_raw.startswith("Table"):
            table_id = table_id_raw
            with data_lock:
                if table_id in tables_status:
                    tables_status[table_id]['status'] = "🔴 LIVE STREAMING"

        if not speech_model:
            return
            
        rec = KaldiRecognizer(speech_model, 16000)
        
        while True:
            data = client_socket.recv(4096)
            if not data: break
            rec.AcceptWaveform(data)
            
        time.sleep(0.1) 

        try:
            result = json.loads(rec.FinalResult())
            spoken_text = result.get("text", "").lower().replace(" and ", " ").replace("please", "")
        except json.JSONDecodeError:
            spoken_text = ""
        
        reply_text = "I didn't quite catch that. Could you say it again?"
        matched_items = []
        
        with data_lock:
            has_pending = len(tables_status.get(table_id, {}).get('pending_orders', [])) > 0

        # Logic branching: Assistance, Confirmation, or Ordering
        if any(word in spoken_text for word in ["help", "manager", "assistance", "staff"]):
            with data_lock:
                if table_id in tables_status:
                    tables_status[table_id]['assistance'] = True
            reply_text = "No worries, I've called a manager over to your table."
            
        elif has_pending:
            # Step 2: Confirmation Loop
            if any(word in spoken_text for word in ["confirm", "yes", "yeah", "correct", "send it"]):
                with data_lock:
                    tables_status[table_id]['orders'].extend(tables_status[table_id]['pending_orders'])
                    tables_status[table_id]['pending_orders'] = []
                reply_text = "Confirmed! I have sent your order to the kitchen."
            elif any(word in spoken_text for word in ["cancel", "no", "wrong", "stop"]):
                with data_lock:
                    tables_status[table_id]['pending_orders'] = []
                reply_text = "No problem, I've cancelled that. What would you like instead?"
            else:
                reply_text = "Please tap the button and say 'Confirm' to order, or 'Cancel' to clear it."
                
        elif spoken_text:
            # Step 1: Initial Order Loop
            remaining_text = spoken_text
            for item in menu_items:
                if item["clean_name"] in remaining_text:
                    matched_items.append(item)
                    remaining_text = remaining_text.replace(item["clean_name"], "", 1)
                    
            if matched_items:
                with data_lock:
                    if table_id in tables_status:
                        for item in matched_items:
                            tables_status[table_id]['pending_orders'].append(f"{item['name']} (£{item['price']:.2f})")
                
                item_counts = Counter([i['name'] for i in matched_items])
                spoken_list = [f"{count} orders of {name}" if count > 1 else name for name, count in item_counts.items()]
                
                if len(spoken_list) == 1:
                    formatted_items = spoken_list[0]
                elif len(spoken_list) == 2:
                    formatted_items = f"{spoken_list[0]} and {spoken_list[1]}"
                else:
                    formatted_items = ", ".join(spoken_list[:-1]) + ", and " + spoken_list[-1]
                    
                reply_text = f"I heard {formatted_items}. Tap the button again and say 'Confirm' to send to the kitchen."

        out_file = f"/tmp/response_{table_id}.raw"
        with open(out_file, "wb") as f:
            subprocess.run(
                [PIPER_EXEC, "--model", PIPER_MODEL, "--output_raw"],
                input=reply_text.encode('utf-8'),
                stdout=f,
                stderr=subprocess.DEVNULL, # Safe terminal
                timeout=10
            )
        
        with open(out_file, "rb") as f:
            client_socket.sendall(f.read())
            
    except socket.timeout:
        pass
    except Exception:
        pass
    finally:
        with data_lock:
            if table_id in tables_status and tables_status[table_id]['status'] == "🔴 LIVE STREAMING":
                tables_status[table_id]['status'] = "Online"
        client_socket.close()

def run_tcp_server() -> None:
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
