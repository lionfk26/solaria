import urequests
import time
import ujson

# --- CORE SETTINGS ---
# Note: The Pi 4B flasher script dynamically modifies the line below for each table
TABLE_ID = "Table_1"
SERVER_URL = "http://192.168.1.100:5000"  # Replace with your actual Pi 4B IP address

def send_event(event_type: str, payload: dict) -> bool:
    """Sends structured data to the central Solaria terminal hub."""
    url = f"{SERVER_URL}/{event_type}"
    headers = {'content-type': 'application/json'}
    data = ujson.dumps(payload)
    
    try:
        response = urequests.post(url, data=data, headers=headers)
        response.close()
        return True
    except Exception as e:
        # Fails silently on the board so a temporary network drop doesn't crash the table unit
        print("Solaria Hub offline or packet dropped:", e)
        return False

# Trigger an automatic registration handshake as soon as the board boots up at the table
send_event("register_table", {"table_id": TABLE_ID})

print(f"[{TABLE_ID}] Runtime system active.")

# --- CORE HARDWARE LOOP ---
while True:
    # This loop runs indefinitely checking your physical hardware.
    # When your physical button/microphone logic triggers an event, 
    # you will execute calls like these:
    
    # 1. Simulating sending an order:
    # send_event("new_order", {"table_id": TABLE_ID, "items": ["1x Burger", "1x Lemonade"]})
    
    # 2. Simulating calling for a waiter:
    # send_event("request_assistance", {"table_id": TABLE_ID, "needs_help": True})
    
    time.sleep(30)  # Keep-alive baseline delay
