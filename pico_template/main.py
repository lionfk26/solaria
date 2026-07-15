import urequests
import time
import ujson
from machine import Pin, I2S

# --- CORE SETTINGS ---
TABLE_ID = "Table_1"
# The Pi will automatically replace <SERVER_IP> with its dynamic local IP on flash
SERVER_URL = "http://<SERVER_IP>:5000"  

# --- HARDWARE SETUP ---
# TTP223 capacitive touch sensor on GP15
touch_sensor = Pin(15, Pin.IN)

# INMP441 Microphone on I2S Bus 0 (Configured for 16kHz raw capture)
audio_in = I2S(0, 
               sck=Pin(16), ws=Pin(17), sd=Pin(18), 
               mode=I2S.RX, 
               bits=16, 
               format=I2S.MONO, 
               rate=16000, 
               ibuf=40000)

# MAX98357A I2S Amplifier on I2S Bus 1 (Configured for 22,050Hz for Piper voice)
audio_out = I2S(1, 
                sck=Pin(20), ws=Pin(21), sd=Pin(22), 
                mode=I2S.TX, 
                bits=16, 
                format=I2S.MONO, 
                rate=22050,  # Matches Piper Northern English model speed perfectly!
                ibuf=40000)

def register():
    """Tells the main server that this client has booted up on the network."""
    try:
        urequests.post(f"{SERVER_URL}/register_table", json={"table_id": TABLE_ID}).close()
    except Exception:
        pass

register()
print(f"[{TABLE_ID}] Ready. Tap touch sensor on GP15 to speak.")

def record_and_send():
    """Records 3 seconds of customer audio and plays the AI vocal reply."""
    print("Recording mic stream...")
    record_time = 3 
    bytes_to_read = 16000 * 2 * record_time
    mic_buffer = bytearray(bytes_to_read)
    
    # Read the data from physical microphone
    audio_in.readinto(mic_buffer)
    print("Uploading recording to Solaria server...")
    
    headers = {'Content-Type': 'application/octet-stream', 'Table-ID': TABLE_ID}
    try:
        response = urequests.post(f"{SERVER_URL}/voice_command", data=mic_buffer, headers=headers)
        reply_audio = response.content
        response.close()
        
        if reply_audio:
            print("Playing local AI voice output...")
            # Stream directly to speaker at 22,050 Hz
            audio_out.write(reply_audio)
    except Exception as e:
        print("Communications failure:", e)

# --- RUNTIME CODE ---
while True:
    if touch_sensor.value() == 1:
        record_and_send()
        time.sleep(2)  # Cooldown prevents accidental multi-triggering
        
    time.sleep(0.1)
