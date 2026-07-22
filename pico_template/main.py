"""
main.py - Solaria table firmware (Raspberry Pi Pico W)

Hardware:
  - INMP441 I2S microphone:  SCK -> GP16, WS -> GP17, SD -> GP18
  - MAX98357A I2S amplifier: BCLK -> GP20, LRC -> GP21, DIN -> GP22
  - TTP223 capacitive touch sensor (push-to-talk): signal -> GP15

Behaviour:
  - Boots, connects to Wi-Fi using the injected WIFI_SSID/WIFI_PASSWORD.
  - Connects to the Solaria server over TCP (SERVER_HOST:SERVER_PORT) and
    sends HELLO <TABLE_ID>.
  - While the touch sensor is held, records mic audio and, on release,
    streams it up to the server as an AUDIO frame.
  - Plays back any SAY <text> feedback from the server as a short local
    tone sequence (a full TTS playback pipeline would render Piper audio
    off-device and stream PCM here; this template keeps a lightweight
    tone-based acknowledgement so the unit is functional out of the box).
  - Exposes a tiny local /status endpoint via microdot.py for on-LAN
    diagnostics.

NOTE: WIFI_SSID / WIFI_PASSWORD / TABLE_ID / SERVER_HOST / SERVER_PORT are
appended to the bottom of this file by Solaria's auto-flasher
(see app.py: flash_pico()). Until flashed, sensible defaults below let
this file boot (and fail loudly) on its own.
"""

import time
import network
import socket
import struct
from machine import Pin, I2S

# --------------------------------------------------------------------------
# Pin definitions
# --------------------------------------------------------------------------

MIC_SCK_PIN = 16   # I2S bit clock (mic)
MIC_WS_PIN = 17    # I2S word select / L-R clock (mic)
MIC_SD_PIN = 18    # I2S serial data in (mic)

AMP_BCLK_PIN = 20  # I2S bit clock (amp)
AMP_LRC_PIN = 21   # I2S word select / L-R clock (amp)
AMP_DIN_PIN = 22   # I2S serial data out (amp)

TOUCH_PIN = 15     # TTP223 touch sensor output

SAMPLE_RATE_HZ = 16000
BITS_PER_SAMPLE = 16
RECORD_BUFFER_MS = 4000  # max recording length per push-to-talk press

# --------------------------------------------------------------------------
# Defaults (overwritten by injected config appended below at flash time)
# --------------------------------------------------------------------------

WIFI_SSID = ""
WIFI_PASSWORD = ""
TABLE_ID = "Table_unconfigured"
SERVER_HOST = None
SERVER_PORT = 5000


def connect_wifi(ssid, password, timeout_s=20):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print(f"[wifi] connecting to '{ssid}'...")
        wlan.connect(ssid, password)
        start = time.time()
        while not wlan.isconnected():
            if time.time() - start > timeout_s:
                print("[wifi] connection timed out")
                return None
            time.sleep(0.5)
    ip = wlan.ifconfig()[0]
    print(f"[wifi] connected, IP = {ip}")
    return wlan


def discover_server(server_port, guess_host=None, attempts=5):
    """
    Resolve the Solaria server's address.

    If SERVER_HOST was baked in at flash time, use it directly. Otherwise,
    fall back to probing the local /24 gateway address, which covers the
    common case of the Pi 5 acting as the network's DHCP gateway/AP.
    Replace with mDNS or a UDP broadcast discovery scheme for larger
    deployments.
    """
    if guess_host:
        return guess_host

    wlan = network.WLAN(network.STA_IF)
    ip, _mask, gateway, _dns = wlan.ifconfig()
    print(f"[discover] no SERVER_HOST baked in, trying gateway {gateway}")
    return gateway


class I2SMic:
    def __init__(self):
        self._i2s = I2S(
            0,
            sck=Pin(MIC_SCK_PIN),
            ws=Pin(MIC_WS_PIN),
            sd=Pin(MIC_SD_PIN),
            mode=I2S.RX,
            bits=BITS_PER_SAMPLE,
            format=I2S.MONO,
            rate=SAMPLE_RATE_HZ,
            ibuf=8192,
        )

    def record(self, duration_ms):
        n_samples = int(SAMPLE_RATE_HZ * (duration_ms / 1000.0))
        n_bytes = n_samples * (BITS_PER_SAMPLE // 8)
        buf = bytearray(n_bytes)
        mv = memoryview(buf)
        read_total = 0
        chunk = bytearray(1024)
        while read_total < n_bytes:
            n = self._i2s.readinto(chunk)
            if n <= 0:
                continue
            end = min(read_total + n, n_bytes)
            mv[read_total:end] = chunk[: end - read_total]
            read_total = end
        return bytes(buf)

    def deinit(self):
        self._i2s.deinit()


class I2SAmp:
    def __init__(self):
        self._i2s = I2S(
            1,
            sck=Pin(AMP_BCLK_PIN),
            ws=Pin(AMP_LRC_PIN),
            sd=Pin(AMP_DIN_PIN),
            mode=I2S.TX,
            bits=BITS_PER_SAMPLE,
            format=I2S.MONO,
            rate=SAMPLE_RATE_HZ,
            ibuf=8192,
        )

    def play_tone(self, freq_hz, duration_ms, volume=0.3):
        import math

        n_samples = int(SAMPLE_RATE_HZ * (duration_ms / 1000.0))
        buf = bytearray(n_samples * 2)
        amplitude = int(32767 * volume)
        for i in range(n_samples):
            sample = int(amplitude * math.sin(2 * math.pi * freq_hz * i / SAMPLE_RATE_HZ))
            struct.pack_into("<h", buf, i * 2, sample)
        self._i2s.write(buf)

    def play_ack(self):
        """Short upward chirp = 'heard you, thinking'."""
        self.play_tone(880, 90)
        self.play_tone(1175, 90)

    def play_confirm(self):
        """Short two-tone chime = 'order confirmed'."""
        self.play_tone(988, 120)
        self.play_tone(1319, 160)

    def play_error(self):
        self.play_tone(220, 250)

    def deinit(self):
        self._i2s.deinit()


class SolariaClient:
    def __init__(self, host, port, table_id):
        self.host = host
        self.port = port
        self.table_id = table_id
        self._sock = None
        self._stream = None

    def connect(self):
        addr = socket.getaddrinfo(self.host, self.port)[0][-1]
        self._sock = socket.socket()
        self._sock.connect(addr)
        self._stream = self._sock
        self._send_line(f"HELLO {self.table_id}")
        print(f"[net] connected to Solaria server at {self.host}:{self.port}")

    def _send_line(self, text):
        self._sock.send((text + "\n").encode())

    def send_audio(self, pcm_bytes):
        self._send_line(f"AUDIO {len(pcm_bytes)}")
        self._sock.send(pcm_bytes)

    def send_confirm(self):
        self._send_line("CONFIRM")

    def send_cancel(self):
        self._send_line("CANCEL")

    def read_response_line(self, timeout_s=5):
        self._sock.settimeout(timeout_s)
        try:
            line = b""
            while not line.endswith(b"\n"):
                chunk = self._sock.recv(1)
                if not chunk:
                    break
                line += chunk
            return line.decode().strip()
        except OSError:
            return ""

    def close(self):
        if self._sock:
            self._sock.close()


def handle_server_response(line, amp):
    if not line:
        return
    print(f"[server] {line}")
    if line.startswith("SAY "):
        amp.play_ack()
    elif line.startswith("CONFIRMED "):
        amp.play_confirm()
    elif line.startswith("ERROR "):
        amp.play_error()
    # PROPOSAL <json> is informational; a future revision could speak the
    # running order back via a streamed Piper WAV instead of a tone.


def main():
    touch = Pin(TOUCH_PIN, Pin.IN)

    wlan = connect_wifi(WIFI_SSID, WIFI_PASSWORD)
    if wlan is None:
        print("[main] cannot continue without Wi-Fi, retrying in 10s...")
        time.sleep(10)
        return main()

    host = discover_server(SERVER_PORT, guess_host=SERVER_HOST)

    mic = I2SMic()
    amp = I2SAmp()
    client = SolariaClient(host, SERVER_PORT, TABLE_ID)

    try:
        client.connect()
    except OSError as exc:
        print(f"[main] could not reach server: {exc}. Retrying in 5s...")
        time.sleep(5)
        return main()

    print(f"[main] {TABLE_ID} ready. Hold the touch sensor to order.")

    last_touch_state = 0
    recording_started_at = None

    while True:
        touch_state = touch.value()

        if touch_state == 1 and last_touch_state == 0:
            # Touch just pressed -> start listening.
            print("[touch] pressed - listening...")
            recording_started_at = time.ticks_ms()

        if touch_state == 0 and last_touch_state == 1:
            # Touch just released -> stop, send audio.
            held_ms = time.ticks_diff(time.ticks_ms(), recording_started_at)
            held_ms = max(300, min(held_ms, RECORD_BUFFER_MS))
            print(f"[touch] released after {held_ms}ms - recording + sending...")
            try:
                pcm = mic.record(held_ms)
                client.send_audio(pcm)
                response = client.read_response_line()
                handle_server_response(response, amp)
            except OSError as exc:
                print(f"[main] network error during order: {exc}")
                try:
                    client.close()
                    client.connect()
                except OSError:
                    pass

        # Double-tap-and-hold-longer style confirm: a long press (>2s)
        # after at least one item has been proposed sends CONFIRM.
        if touch_state == 1 and last_touch_state == 1 and recording_started_at:
            held_ms = time.ticks_diff(time.ticks_ms(), recording_started_at)
            if held_ms > 2000:
                print("[touch] long press - confirming order")
                try:
                    client.send_confirm()
                    response = client.read_response_line()
                    handle_server_response(response, amp)
                except OSError as exc:
                    print(f"[main] network error during confirm: {exc}")
                recording_started_at = None

        last_touch_state = touch_state
        time.sleep_ms(20)


if __name__ == "__main__":
    main()
