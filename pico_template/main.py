import urequests
import usocket
import time
from machine import Pin, I2S

# --- RUNTIME CORE SETTINGS ---
TABLE_ID = "Table_1"
SERVER_IP = "<SERVER_IP>"  # Automatically provisioned via auto-flasher

# --- PIN MAP DEFINITIONS ---
touch_sensor = Pin(15, Pin.IN)

# INMP441 Microchip Configuration (16kHz Audio Sample Collection Rate)
audio_in = I2S(0, 
               sck=Pin(16), ws=Pin(17), sd=Pin(18), 
               mode=I2S.RX, bits=16, format=I2S.MONO, 
               rate=16000, ibuf=10000)

# MAX98357A Output Configuration (16kHz for clean pipeline sync)
audio_out = I2S(1, 
                sck=Pin(20), ws=Pin(21), sd=Pin(22), 
                mode=I2S.TX, bits=16, format=I2S.MONO, 
                rate=16000, ibuf=10000)

# Synchronize base presence via HTTP API Layer
try:
    urequests.post(f"http://{SERVER_IP}:5000/register_table", json={"table_id": TABLE_ID}).close()
except Exception:
    pass

print(f"[{TABLE_ID}] Live System Active. Tap once to START streaming, tap again to SEND.")

def execute_live_stream():
    # RELEASE GUARD: Wait for the user to lift their finger off the button first!
    while touch_sensor.value() == 1:
        time.sleep(0.05)
    time.sleep(0.1) # Final debounce
    
    print("🔴 Live socket transmission established...")
    
    s = usocket.socket()
    try:
        s.connect((SERVER_IP, 5001))
    except Exception as e:
        print("Connection failure to Stream Server Target:", e)
        return
        
    # Standardize table allocation block footprint header to exactly 10 bytes
    identity_header = (TABLE_ID + "          ")[:10]
    s.send(identity_header.encode())
    
    # Process small audio slice footprints to bypass device internal RAM limits
    audio_slice_buffer = bytearray(4000) 
    
    while True:
        try:
            audio_in.readinto(audio_slice_buffer)
            s.send(audio_slice_buffer)
        except OSError:
            continue # Skip minor hardware pipeline glitches
            
        # Monitor interface input line to trigger cessation commands
        if touch_sensor.value() == 1:
            print("⏹️ Termination trigger detected. Closing feed and awaiting processing output...")
            break
            
    # Terminate the outbound write channel to signal the data compilation layer
    s.shutdown(usocket.SHUT_WR)
    
    print("🔊 Initializing audio rendering pipeline...")
    while True:
        try:
            response_chunk = s.recv(4096)
            if not response_chunk:
                break
            audio_out.write(response_chunk)
        except Exception:
            break
            
    s.close()
    print("✨ Transmission sequence finalized successfully.")

# --- PERSISTENT POLLING LOOP ---
while True:
    if touch_sensor.value() == 1:
        execute_live_stream()
        time.sleep(1.5)  # Global operational loop reset lockout protection
    time.sleep(0.1)
