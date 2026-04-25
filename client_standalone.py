import os
import sys
import time
import random
import json
import uuid
import base64
import io
import logging
import threading
import asyncio
import subprocess
import platform
import aiohttp

# Configure logging early
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- External Dependencies with Fallbacks ---
try:
    import mss
    from PIL import Image
    SCREENSHOT_AVAILABLE = True
except ImportError:
    SCREENSHOT_AVAILABLE = False

try:
    import pytesseract
    OCR_AVAILABLE = True
    
    # --- Tesseract Configuration for Bundled App ---
    if getattr(sys, 'frozen', False):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
        # We'll bundle the binary as 'tesseract-bin' to avoid confusion with the package
        tesseract_bin = os.path.join(base_path, 'tesseract')
        tessdata_dir = os.path.join(base_path, 'tessdata')
        
        if os.path.exists(tesseract_bin):
            pytesseract.pytesseract.tesseract_cmd = tesseract_bin
            os.environ['TESSDATA_PREFIX'] = base_path
            logging.info(f"Using bundled Tesseract: {tesseract_bin}")
        else:
            logging.warning(f"Bundled Tesseract not found at: {tesseract_bin}")
except ImportError:
    OCR_AVAILABLE = False

try:
    from pynput import keyboard as pynput_keyboard
    KEYBOARD_AVAILABLE = True
    keyboard_controller = pynput_keyboard.Controller()
except ImportError:
    KEYBOARD_AVAILABLE = False
    keyboard_controller = None

# ==========================================
# LED Controller Logic
# ==========================================
class LEDController:
    def __init__(self):
        self.os_type = platform.system().lower()
        if self.os_type == "linux":
            try:
                subprocess.run(["xmodmap", "-e", "add mod3 = Scroll_Lock"], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except: pass
        
    def _toggle_led(self, led_name: str):
        if self.os_type != "linux": return False, "Linux only"
        key_map = {"Caps Lock": "Caps_Lock", "Num Lock": "Num_Lock", "Scroll Lock": "Scroll_Lock"}
        key = key_map.get(led_name)
        if not key: return False, "Invalid LED"
        try:
            # We use xdotool for the key state and light
            result = subprocess.run(["xdotool", "key", key], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0: return True, f"Toggled {led_name}"
            elif led_name == "Scroll Lock":
                subprocess.run(["xset", "led", "3"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True, "Fallback xset"
            return False, "Failed"
        except: return False, "Error"

    def set_caps_lock(self, state: bool): return self._toggle_led("Caps Lock")
    def set_num_lock(self, state: bool): return self._toggle_led("Num Lock")
    def set_scroll_lock(self, state: bool): return self._toggle_led("Scroll Lock")

    def blink_all_until_stopped(self, stop_event: threading.Event, pause_event: threading.Event = None):
        def _blink():
            while not stop_event.is_set():
                if pause_event and pause_event.is_set():
                    time.sleep(0.1); continue
                self._toggle_led("Num Lock"); self._toggle_led("Caps Lock"); self._toggle_led("Scroll Lock")
                for _ in range(4):
                    if stop_event.is_set(): break
                    time.sleep(0.1)
                if stop_event.is_set(): break
                if pause_event and pause_event.is_set(): continue
                self._toggle_led("Num Lock"); self._toggle_led("Caps Lock"); self._toggle_led("Scroll Lock")
                for _ in range(3):
                    if stop_event.is_set(): break
                    time.sleep(0.1)
        threading.Thread(target=_blink, daemon=True).start()

    def sweep_loop(self, number: int, stop_event: threading.Event, pause_event: threading.Event = None):
        num = abs(number)
        if num == 0:
            self.set_caps_lock(False); self.set_num_lock(False); self.set_scroll_lock(False)
            return True, "Off"
        def _sweep():
            leds = ["Num Lock", "Caps Lock", "Scroll Lock"]
            while not stop_event.is_set():
                if pause_event and pause_event.is_set():
                    time.sleep(0.1); continue
                for i in range(num):
                    if stop_event.is_set(): break
                    while pause_event and pause_event.is_set() and not stop_event.is_set(): time.sleep(0.1)
                    led = leds[i % 3]
                    self._toggle_led(led); time.sleep(0.25); self._toggle_led(led); time.sleep(0.1)
                if not stop_event.is_set():
                    for _ in range(10):
                        if stop_event.is_set(): break
                        while pause_event and pause_event.is_set() and not stop_event.is_set(): time.sleep(0.1)
                        time.sleep(0.1)
        threading.Thread(target=_sweep, daemon=True).start()
        return True, f"Sweep {num}"

led_controller = LEDController()

# ==========================================
# Human Typing Logic
# ==========================================
class HumanTypingSimulator:
    def __init__(self, wpm: int = 200, mistake_chance: float = 0.15):
        self.wpm = max(1, wpm)
        self.mistake_chance = mistake_chance
        self.base_delay = 1.0 / ((self.wpm * 5) / 60.0)
        self.nearby_keys = {'a': 'qwsz', 'b': 'vghn', 'c': 'xdfv', 'd': 'ersfcx', 'e': 'wsdr', 'f': 'rtgvcd', 'g': 'tyhbvf', 'h': 'yujnbg', 'i': 'ujko', 'j': 'uikmnh', 'k': 'ijolm', 'l': 'opk', 'm': 'njk', 'n': 'bhjm', 'o': 'iklp', 'p': 'ol', 'q': 'wa', 'r': 'edft', 's': 'awedxz', 't': 'rfgy', 'u': 'yhij', 'v': 'cfgb', 'w': 'qase', 'x': 'zsdc', 'y': 'tghu', 'z': 'asx'}

    def _get_delay(self, char: str, speed: float) -> float:
        d = self.base_delay * random.lognormvariate(-0.03, 0.25)
        if char == ' ': d *= 0.6
        if char.isupper(): d += 0.1
        if not char.isalnum(): d += 0.3
        return max(0.01, d * speed)

    def generate_events(self, text: str):
        i = 0; speed = 1.0
        while i < len(text):
            char = text[i]
            if random.random() < self.mistake_chance and char.isalpha():
                typo = random.choice(self.nearby_keys.get(char.lower(), 'q'))
                yield ('type', typo, self._get_delay(typo, speed))
                time.sleep(0.3)
                yield ('backspace', '', 0.1)
            yield ('type', char, self._get_delay(char, speed))
            i += 1

    def type_out_gui(self, text: str, cancel_event=None, pause_event=None):
        if not KEYBOARD_AVAILABLE: return False
        for action, char, delay in self.generate_events(text):
            if cancel_event and cancel_event.is_set(): return False
            while pause_event and pause_event.is_set(): time.sleep(0.1)
            time.sleep(delay)
            try:
                if action == 'type': keyboard_controller.type(char)
                elif action == 'backspace': keyboard_controller.tap(pynput_keyboard.Key.backspace)
            except: pass
        return True

# ==========================================
# Network Client Logic
# ==========================================
class NetworkClient:
    def __init__(self, host='led-server-production-5f97.up.railway.app', port=8888, on_message=None, app=None):
        self.url = f"wss://{host}/ws" if "up.railway.app" in host else f"ws://{host}:{port}/ws"
        self.ws = None; self.is_connected = False; self.should_run = True; self.on_message = on_message
        self.app = app; self.loop = None

    def connect(self):
        self.should_run = True
        threading.Thread(target=self._start_loop, daemon=True).start()

    def _start_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._run_loop())

    async def _run_loop(self):
        while self.should_run:
            if not self.is_connected:
                try:
                    # Disable SSL verification for localhost and Railway domains due to hostname mismatch issues
                    ssl_context = False if ("localhost" in self.url or "up.railway.app" in self.url) else None
                    async with aiohttp.ClientSession() as session:
                        async with session.ws_connect(self.url, ssl=ssl_context) as ws:
                            self.ws = ws; self.is_connected = True
                            logging.info(f"Connected to {self.url}")
                            await self._send_async({"type": "status", "ready": False})
                            self._trigger_ack()
                            async for msg in ws:
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    if self.on_message: self.on_message(json.loads(msg.data))
                            self.is_connected = False
                except Exception as e:
                    logging.error(f"Conn failed: {e}"); await asyncio.sleep(5)
            else: await asyncio.sleep(1)

    def _trigger_ack(self):
        stop = threading.Event()
        led_controller.blink_all_until_stopped(stop, self.app.pause_event)
        def _wait():
            logging.info("Awaiting acknowledgment (Ctrl key)...")
            self.app.await_ack(stop)
            self.send_message({"type": "status", "ready": True})
            logging.info("Handshake complete.")
        threading.Thread(target=_wait, daemon=True).start()

    def send_message(self, msg: dict):
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._send_async(msg), self.loop)

    async def _send_async(self, msg: dict):
        if self.ws:
            try: await self.ws.send_json(msg)
            except: self.is_connected = False

    def send_feedback(self, status, msg, action):
        self.send_message({"type": "feedback", "status": status, "message": msg, "action": action})

    def disconnect(self): self.should_run = False

# ==========================================
# Typing Handler Logic
# ==========================================
class TypingHandler:
    def __init__(self, app):
        self.app = app
        self.simulator = HumanTypingSimulator()
        self._is_typing = False; self._blink_active = False

    def type_text(self, text, on_complete):
        if self._is_typing: return False, "Busy"
        self._is_typing = True
        def _run():
            self._blink_active = True
            def _blink():
                while self._blink_active:
                    if self.app.cancel_event.is_set(): break
                    while self.app.pause_event.is_set() and not self.app.cancel_event.is_set(): time.sleep(0.1)
                    led_controller.set_caps_lock(True); time.sleep(0.3); led_controller.set_caps_lock(False); time.sleep(0.3)
            threading.Thread(target=_blink, daemon=True).start()
            
            logging.info("Waiting for End key to start typing...")
            self.app.await_trigger(pynput_keyboard.Key.end)
            
            self._blink_active = False
            if self.app.cancel_event.is_set():
                self._is_typing = False
                on_complete("cancelled", "User cancelled")
                return
                
            logging.info(f"Typing started ({len(text)} chars)...")
            self.simulator.type_out_gui(text, self.app.cancel_event, self.app.pause_event)
            self._is_typing = False
            on_complete("success", "Typing complete")
        threading.Thread(target=_run, daemon=True).start()
        return True, "Waiting for trigger"

# ==========================================
# Screenshot Handler Logic
# ==========================================
class ScreenshotHandler:
    def __init__(self, network):
        self.network = network; self.should_run = False

    def start(self):
        if not SCREENSHOT_AVAILABLE: return
        self.should_run = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        # Use MSS (class) instead of mss (module function) to fix deprecation warning
        with mss.MSS() as sct:
            while self.should_run:
                if self.network.is_connected:
                    try:
                        monitor = sct.monitors[1]
                        sct_img = sct.grab(monitor)
                        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                        img.thumbnail((1280, 720))
                        buf = io.BytesIO(); img.save(buf, format="JPEG", quality=40)
                        self.network.send_message({"type": "screenshot", "data": base64.b64encode(buf.getvalue()).decode()})
                        if OCR_AVAILABLE:
                            text = pytesseract.image_to_string(img)
                            self.network.send_message({"type": "ocr_text", "data": text.strip()})
                    except: pass
                time.sleep(5)

    def stop(self): self.should_run = False

# ==========================================
# Main Application
# ==========================================
class Application:
    def __init__(self):
        self.pause_event = threading.Event()
        self.cancel_event = threading.Event()
        self.trigger_event = threading.Event()
        self.ack_event = threading.Event()
        
        self.network = NetworkClient(on_message=self.handle_msg, app=self)
        self.typing_handler = TypingHandler(self)
        self.screenshot_handler = ScreenshotHandler(self.network)
        
        self._last_hotkey_time = 0
        self._start_global_listener()

    def _start_global_listener(self):
        if not KEYBOARD_AVAILABLE: return
        def _on_press(key):
            now = time.time()
            if now - self._last_hotkey_time < 0.2: return # Debounce
            
            if key == pynput_keyboard.Key.insert:
                self._last_hotkey_time = now
                if self.pause_event.is_set(): self.pause_event.clear(); logging.info("Resumed (Insert)")
                else: self.pause_event.set(); logging.info("Paused (Insert)")
            elif key in [pynput_keyboard.Key.ctrl, pynput_keyboard.Key.ctrl_l, pynput_keyboard.Key.ctrl_r]:
                self._last_hotkey_time = now
                self.cancel_event.set(); self.ack_event.set(); logging.info("Action Cancelled/Acknowledged")
            elif key == pynput_keyboard.Key.end:
                self.trigger_event.set()
                
        l = pynput_keyboard.Listener(on_press=_on_press)
        l.daemon = True
        l.start()

    def await_ack(self, stop_blink_event):
        self.ack_event.clear()
        while not self.ack_event.is_set():
            time.sleep(0.1)
        stop_blink_event.set()

    def await_trigger(self, target_key):
        self.trigger_event.clear()
        while not self.trigger_event.is_set() and not self.cancel_event.is_set():
            time.sleep(0.1)

    def handle_msg(self, msg):
        t, d = msg.get("type"), msg.get("data")
        if t == "number":
            self.cancel_event.clear(); self.pause_event.clear()
            num = d[-1] if isinstance(d, list) else d
            led_controller.sweep_loop(num, self.cancel_event, self.pause_event)
            def _wait_feedback():
                self.ack_event.clear()
                self.ack_event.wait()
                self.network.send_feedback("success", f"Number {num} acknowledged", "number")
            threading.Thread(target=_wait_feedback, daemon=True).start()
        elif t == "text":
            self.cancel_event.clear(); self.pause_event.clear()
            self.typing_handler.type_text(str(d), lambda s, m: self.network.send_feedback(s, m, "text"))

    def run(self):
        self.network.connect(); self.screenshot_handler.start()
        print("--- Standalone Client (v2) ---")
        print("Hotkeys: Insert=Pause, Ctrl=Cancel/Ack, End=Start Typing")
        while True:
            try:
                cmd = input("client> ").strip().lower()
                if cmd in ["exit", "quit"]: break
            except EOFError: break
        self.network.disconnect(); self.screenshot_handler.stop()

if __name__ == "__main__":
    try: Application().run()
    except KeyboardInterrupt: pass
