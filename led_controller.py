import subprocess
import platform
import logging
import threading
import time

class LEDController:
    """Controls keyboard LEDs across different platforms.
    For Linux, it uses the `xset` command.
    """
    def __init__(self):
        self.os_type = platform.system().lower()
        if self.os_type == "linux":
            # On many Linux distros (Kali, Ubuntu), Scroll Lock LED is disabled by default.
            # This command maps Scroll Lock to the mod3 modifier, enabling the LED.
            try:
                subprocess.run(["xmodmap", "-e", "add mod3 = Scroll_Lock"], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except:
                pass
        
    def _toggle_led(self, led_name: str):
        if self.os_type != "linux":
            return False, "Not supported on non-Linux OS without additional setup"
            
        # Use xdotool to physically toggle the LED key
        key_map = {
            "Caps Lock": "Caps_Lock",
            "Num Lock": "Num_Lock",
            "Scroll Lock": "Scroll_Lock"
        }
        key = key_map.get(led_name)
        if not key:
            return False, "Invalid LED name"
            
        try:
            result = subprocess.run(
                ["xdotool", "key", key],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode == 0:
                return True, f"Toggled {led_name}"
            else:
                # Fallback to xset only if xdotool fails
                if led_name == "Scroll Lock":
                    subprocess.run(["xset", "led", "3"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return True, "Toggled Scroll Lock via xset fallback"
                return False, f"xdotool failed: {result.stderr}"
        except Exception as e:
            return False, f"Exception running xdotool: {e}"

    def set_caps_lock(self, state: bool):
        # We can't strictly enforce state with xdotool toggle, but we can toggle it
        return self._toggle_led("Caps Lock")

    def set_num_lock(self, state: bool):
        return self._toggle_led("Num Lock")

    def set_scroll_lock(self, state: bool):
        return self._toggle_led("Scroll Lock")

    def blink_all_until_stopped(self, stop_event: threading.Event, pause_event: threading.Event = None):
        """Blink all three LEDs simultaneously until stop_event is set (used on connect)."""
        def _blink():
            while not stop_event.is_set():
                if pause_event and pause_event.is_set():
                    time.sleep(0.1)
                    continue
                    
                self._toggle_led("Num Lock")
                self._toggle_led("Caps Lock")
                self._toggle_led("Scroll Lock")
                
                # Check for stop/pause during sleep
                for _ in range(4):
                    if stop_event.is_set(): break
                    time.sleep(0.1)
                
                if stop_event.is_set(): break
                if pause_event and pause_event.is_set(): continue

                self._toggle_led("Num Lock")
                self._toggle_led("Caps Lock")
                self._toggle_led("Scroll Lock")
                
                for _ in range(3):
                    if stop_event.is_set(): break
                    time.sleep(0.1)
        threading.Thread(target=_blink, daemon=True).start()

    def sweep_connection(self):
        """Quick LED sweep to indicate successful connection (legacy one-shot)."""
        def _sweep():
            for led in ["Caps Lock", "Num Lock", "Scroll Lock", "Num Lock", "Caps Lock"]:
                self._toggle_led(led)
                time.sleep(0.15)
                self._toggle_led(led)
        threading.Thread(target=_sweep, daemon=True).start()


    def sweep_loop(self, number: int, stop_event: threading.Event, pause_event: threading.Event = None):
        """Sequentially sweep N LEDs repeatedly with a delay."""
        num = abs(number)
        if num == 0:
            self.set_caps_lock(False)
            self.set_num_lock(False)
            self.set_scroll_lock(False)
            return True, "Turned off all LEDs"
            
        def _sweep():
            leds = ["Num Lock", "Caps Lock", "Scroll Lock"]
            while not stop_event.is_set():
                if pause_event and pause_event.is_set():
                    time.sleep(0.1)
                    continue
                    
                for i in range(num):
                    if stop_event.is_set(): break
                    while pause_event and pause_event.is_set() and not stop_event.is_set():
                        time.sleep(0.1)
                        
                    led = leds[i % 3]
                    self._toggle_led(led)
                    time.sleep(0.25)
                    self._toggle_led(led)
                    time.sleep(0.1)
                    
                if not stop_event.is_set():
                    # 1 second delay in chunks to remain responsive
                    for _ in range(10):
                        if stop_event.is_set(): break
                        while pause_event and pause_event.is_set() and not stop_event.is_set():
                            time.sleep(0.1)
                        time.sleep(0.1)
                    
            pass
                
        threading.Thread(target=_sweep, daemon=True).start()
        return True, f"Started sweep loop for number {num}"

# Global instance
led_controller = LEDController()
