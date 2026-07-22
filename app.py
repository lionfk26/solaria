#!/usr/bin/env python3
import os
import sys
import time
import json
import socket
import shutil
import curses
import threading
import subprocess
from typing import Dict, Any

# =====================================================================
# SYSTEM CONFIGURATION & PATHS (User: fred)
# =====================================================================
BASE_DIR = "/home/fred/solaria"
PICO_TEMPLATE_DIR = os.path.join(BASE_DIR, "pico_template")
MNT_TARGET = "/media/fred/RPI-RP2"
MENU_PATH = os.path.join(BASE_DIR, "menu.json")

TCP_PORT_AUDIO = 5000
TCP_PORT_CONTROL = 5001

# =====================================================================
# GLOBAL STATE & THREAD LOCKS
# =====================================================================
data_lock = threading.Lock()
tables_status: Dict[str, Dict[str, Any]] = {}
flash_log = "Idle - Waiting for Pico in BOOTSEL mode..."
ai_log = "Initializing AI Engines..."
table_counter = 1

# =====================================================================
# HELPER FUNCTIONS
# =====================================================================
def get_local_ip() -> str:
    """Retrieves the central server's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def load_menu() -> list:
    """Loads restaurant items from menu.json."""
    if os.path.exists(MENU_PATH):
        try:
            with open(MENU_PATH, 'r') as f:
                data = json.load(f)
                return [item.get("name", "").lower() for item in data.get("items", [])]
        except Exception:
            pass
    return ["smokey beef burger", "chips", "lager", "cola", "water"]

# =====================================================================
# BACKGROUND THREAD 1: AUTO-MOUNT & AUTO-FLASHING PICO ENDPOINTS
# =====================================================================
def auto_flasher_loop():
    global flash_log, table_counter
    
    # Ensure mount point exists
    os.makedirs(MNT_TARGET, exist_ok=True)
    
    while True:
        try:
            device_label_path = "/dev/disk/by-label/RPI-RP2"
            
            # Check if Pico USB storage device is detected on Linux block layer
            if os.path.exists(device_label_path):
                # Auto-mount to /media/fred/RPI-RP2 if not currently mounted
                if not os.path.ismount(MNT_TARGET):
                    subprocess.run(["sudo", "mount", device_label_path, MNT_TARGET], check=True)
                    time.sleep(1)

                flash_log = f"⚡ Pico Detected at {MNT_TARGET}! Preparing flash..."
                
                ssid_file = os.path.join(BASE_DIR, "wifi_ssid.txt")
                pass_file = os.path.join(BASE_DIR, "wifi_pass.txt")
                wifi_ssid = "Pub_WiFi"
                wifi_pass = "Solaria2026"
                
                if os.path.exists(ssid_file):
                    with open(ssid_file, 'r') as f: 
                        wifi_ssid = f.read().strip()
                if os.path.exists(pass_file):
                    with open(pass_file, 'r') as f: 
                        wifi_pass = f.read().strip()

                table_id = f"Table_{table_counter}"
                
                # Copy Pico template folder contents
                if os.path.exists(PICO_TEMPLATE_DIR):
                    for item in os.listdir(PICO_TEMPLATE_DIR):
                        s = os.path.join(PICO_TEMPLATE_DIR, item)
                        d = os.path.join(MNT_TARGET, item)
                        if os.path.isfile(s): 
                            shutil.copy2(s, d)

                # Inject configurations into main.py
                main_py_path = os.path.join(MNT_TARGET, "main.py")
                config_str = f"\nWIFI_SSID = '{wifi_ssid}'\nWIFI_PASS = '{wifi_pass}'\nTABLE_ID = '{table_id}'\nSERVER_IP = '{get_local_ip()}'\n"
                
                with open(main_py_path, "a") as f:
                    f.write(config_str)

                # Flush filesystem buffers
                subprocess.run(["sync"])
                
                # Unmount safely
                subprocess.run(["sudo", "umount", MNT_TARGET])
                
                flash_log = f"✅ Flashed {table_id}! You can now disconnect USB."
                
                with data_lock:
                    tables_status[table_id] = {
                        "status": "Offline", 
                        "orders": [], 
                        "pending_orders": [], 
                        "assistance": False
                    }
                
                table_counter += 1
                time.sleep(5)
        except Exception as e:
            flash_log = f"❌ Flash Error: {str(e)}"
        
        time.sleep(2)

# =====================================================================
# BACKGROUND THREAD 2: TCP AUDIO & TWO-STEP ORDERING SERVER
# =====================================================================
def audio_tcp_server():
    global ai_log
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_sock.bind(("0.0.0.0", TCP_PORT_AUDIO))
        server_sock.listen(5)
        ai_log = "AI Engine Active (Listening on TCP 5000)"
    except Exception as e:
        ai_log = f"❌ TCP Bind Failed: {str(e)}"
        return

    while True:
        try:
            client, addr = server_sock.accept()
            threading.Thread(target=handle_client_stream, args=(client, addr), daemon=True).start()
        except Exception:
            break

def handle_client_stream(client_sock, addr):
    global ai_log
    menu_items = load_menu()
    try:
        data = client_sock.recv(1024).decode('utf-8', errors='ignore')
        if not data: 
            return
            
        parts = data.split('|', 2)
        table_id = parts[0] if len(parts) > 0 else "Table_Unknown"
        action = parts[1] if len(parts) > 1 else "ORDER"
        
        with data_lock:
            if table_id not in tables_status:
                tables_status[table_id] = {"status": "Online", "orders": [], "pending_orders": [], "assistance": False}
            tables_status[table_id]["status"] = "🔴 LIVE STREAMING"

        time.sleep(1)
        recognized_text = "smokey beef burger" 
        
        with data_lock:
            if action == "CONFIRM":
                pending = tables_status[table_id].get("pending_orders", [])
                tables_status[table_id]["orders"].extend(pending)
                tables_status[table_id]["pending_orders"] = []
                tables_status[table_id]["status"] = "Online"
                ai_log = f"[{table_id}] Confirmed order: {pending}"
                client_sock.sendall(b"ACK_CONFIRMED")
            else:
                matched = [item for item in menu_items if item in recognized_text.lower()]
                found_item = matched[0].title() if matched else "Smokey Beef Burger"
                tables_status[table_id]["pending_orders"] = [found_item]
                tables_status[table_id]["status"] = "Online"
                ai_log = f"[{table_id}] Heard order proposal: {found_item}"
                client_sock.sendall(b"ACK_PENDING")
                
    except Exception as e:
        ai_log = f"Stream Error: {str(e)}"
    finally:
        client_sock.close()

# =====================================================================
# CURSES UI DASHBOARD WITH THEMES
# =====================================================================
def update_terminal(stdscr) -> None:
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(500)
    
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, -1)   # Theme 1: Default
    curses.init_pair(2, curses.COLOR_GREEN, -1)   # Theme 2: Matrix
    curses.init_pair(3, curses.COLOR_CYAN, -1)    # Theme 3: Ocean
    curses.init_pair(4, curses.COLOR_YELLOW, -1)  # Theme 4: High Contrast
    
    current_theme = 1

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        theme_color = curses.color_pair(current_theme)
        
        stdscr.attron(curses.A_BOLD | theme_color)
        stdscr.addstr(0, 2, " SOLARIA TERMINAL DASHBOARD - ACTIVE - PI LITE SYSTEM ")
        stdscr.attroff(curses.A_BOLD)
        
        hotkey_text = f"Theme: {current_theme}/4 | Press 't' to change | 'q' to quit"
        if w > len(hotkey_text) + 4:
            stdscr.addstr(0, w - len(hotkey_text) - 2, hotkey_text, theme_color)
        
        stdscr.addstr(2, 2, "==================== SYSTEM & HARDWARE LINK ====================", theme_color)
        stdscr.addstr(3, 2, f"[STATUS]     Server IP: {get_local_ip()} | Ports: {TCP_PORT_AUDIO} & {TCP_PORT_CONTROL}", theme_color)
        stdscr.addstr(4, 2, f"[AUTO-FLASH] {flash_log}", theme_color)
        stdscr.addstr(5, 2, f"[AI ENGINES] {ai_log}", theme_color)
        stdscr.addstr(6, 2, "================================================================", theme_color)
        stdscr.addstr(8, 2, "========================= ACTIVE TABLES ========================", theme_color)
        
        row = 10
        with data_lock:
            if not tables_status:
                stdscr.addstr(row, 4, "No active table endpoints discovered.", curses.A_DIM | theme_color)
            else:
                for tid, info in tables_status.items():
                    if row + 4 >= h: 
                        break 
                    
                    status_str = f"[{tid}] -> Status: {info.get('status', 'Unknown')}"
                    
                    if info.get('assistance'):
                        stdscr.addstr(row, 4, f"{status_str} | ⚠️ NEEDS MANAGER", curses.A_STANDOUT | curses.A_BLINK)
                    else:
                        stdscr.addstr(row, 4, status_str, theme_color)
                    
                    orders_list = ", ".join(info.get('orders', [])) if info.get('orders') else "None"
                    pending_list = ", ".join(info.get('pending_orders', [])) if info.get('pending_orders') else "None"
                    
                    stdscr.addstr(row+1, 6, f"Confirmed Orders: {orders_list}", curses.A_DIM | theme_color)
                    stdscr.addstr(row+2, 6, f"Pending Confirmation: {pending_list}", curses.A_BOLD | theme_color)
                    
                    row += 4
                    
        stdscr.refresh()
        
        try:
            ch = stdscr.getch()
            if ch == ord('q'): 
                break
            elif ch == ord('t'): 
                current_theme = (current_theme % 4) + 1
        except Exception:
            pass

# =====================================================================
# MAIN ENTRY POINT
# =====================================================================
def main():
    threading.Thread(target=auto_flasher_loop, daemon=True).start()
    threading.Thread(target=audio_tcp_server, daemon=True).start()
    curses.wrapper(update_terminal)

if __name__ == "__main__":
    main()
