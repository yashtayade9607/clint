import sys
import os
import threading
import logging
import time

# Add parent directory to path so we can import from 'scaning' dir
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

try:
    from human_typing import HumanTypingSimulator, KEYBOARD_AVAILABLE, pynput_keyboard
    SIMULATOR_AVAILABLE = True
except ImportError:
    SIMULATOR_AVAILABLE = False
    KEYBOARD_AVAILABLE = False

from led_controller import led_controller

class TypingHandler:
    def __init__(self):
        self.simulator = None
        self._is_typing = False
        self._blink_active = False
        if SIMULATOR_AVAILABLE:
            self.simulator = HumanTypingSimulator(wpm=80, mistake_chance=0.15)

    def is_available(self):
        return SIMULATOR_AVAILABLE and KEYBOARD_AVAILABLE

    def type_text(self, text: str, cancel_event=None, pause_event=None, on_complete=None):
        if not self.is_available():
            if on_complete: on_complete("error", "Typing simulator or pynput not available.")
            return False, "Typing simulator or pynput not available."

        if self._is_typing:
            if on_complete: on_complete("error", "Already waiting for End key or typing.")
            return False, "Already waiting for End key or typing."
            
        self._is_typing = True

        def run_typing():
            self._blink_active = True
            
            # Start continuous blinking loop (all together)
            def blink_loop():
                while self._blink_active:
                    if cancel_event and cancel_event.is_set():
                        break
                    while pause_event and pause_event.is_set() and not cancel_event.is_set():
                        time.sleep(0.1)
                        
                    # Turn ON all
                    led_controller._toggle_led("Num Lock")
                    led_controller._toggle_led("Caps Lock")
                    led_controller._toggle_led("Scroll Lock")
                    time.sleep(0.3)
                    # Turn OFF all
                    led_controller._toggle_led("Num Lock")
                    led_controller._toggle_led("Caps Lock")
                    led_controller._toggle_led("Scroll Lock")
                    time.sleep(0.3)
                    
                # Ensure all are turned off when stopping
                led_controller.set_caps_lock(False)
                led_controller.set_num_lock(False)
                led_controller.set_scroll_lock(False)

            threading.Thread(target=blink_loop, daemon=True).start()

            triggered = False
            
            # Key listener to detect 'End' key
            def on_press(key):
                nonlocal triggered
                if key == pynput_keyboard.Key.end:
                    triggered = True
                    return False # Stop listener

            logging.info("Waiting for 'End' key...")
            
            # Use loop to allow pausing while listening
            while not (cancel_event and cancel_event.is_set()) and not triggered:
                if pause_event and pause_event.is_set():
                    time.sleep(0.1)
                    continue
                    
                with pynput_keyboard.Listener(on_press=on_press) as listener:
                    listener.join()
                
            self._blink_active = False
            time.sleep(1) # wait for blinking to stop and user to release keys

            if cancel_event and cancel_event.is_set():
                self._is_typing = False
                if on_complete: on_complete("cancelled", "Typing cancelled by user.")
                return

            logging.info(f"Trigger detected! Typing {len(text)} characters...")
            try:
                success = self.simulator.type_out_gui(text, cancel_event=cancel_event, pause_event=pause_event)
                if success:
                    if on_complete: on_complete("success", "Typing completed successfully.")
                else:
                    if on_complete: on_complete("cancelled", "Typing cancelled by user.")
            except Exception as e:
                logging.error(f"Error during typing: {e}")
                if on_complete: on_complete("error", f"Typing error: {e}")
            finally:
                self._is_typing = False

        # Run typing logic in a separate daemon thread
        t = threading.Thread(target=run_typing, daemon=True)
        t.start()
        return True, f"Waiting for 'End' key before typing {len(text)} characters."

typing_handler = TypingHandler()
