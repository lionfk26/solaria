import urequests
import time
import ujson

# --- CORE SETTINGS ---
TABLE_ID = "Table_1"
SERVER_URL = "http://192.168.1.100:5000"  # Remember to replace this with your Pi 4B's static IP address!

def send_event(event_type: str, payload: dict) -> bool:
    """Sends structured data payloads to the main Solaria hub."""
    url = f"{SERVER_URL}/{event_type}"
    headers = {'content-type': 'application/json'}
    data = ujson.dumps(payload)
    
    try:
        response = urequests.post(url, data=data, headers=headers)
        response.close()
        return True
    except Exception as e:
        print("Network connection trace failure:", e)
        return False

# Self-register with server upon power-up initialization
send_event("register_table", {"table_id": TABLE_ID})

print(f"[{TABLE_ID}] Ready to process loops.")

while True:
    # Your hardware-triggered loops and inputs live inside this area.
    # Un-comment the line below inside a trial unit to simulate an automatic test order:
    # send_event("new_order", {"table_id": TABLE_ID, "items": ["1x Pizza", "1x Cola"]})
    
    time.sleep(30)
