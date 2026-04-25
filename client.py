import logging
import sys
import threading
from network import TCPClient
from led_controller import led_controller
from typing_handler import typing_handler
from screenshot_handler import ScreenshotHandler

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class Application:
    def __init__(self):
        self.auto_control_enabled = True
        self.pause_event = threading.Event()
        self.cancel_event = threading.Event()
        self.network = TCPClient(on_message=self.handle_server_message, pause_event=self.pause_event)
        self.screenshot_handler = ScreenshotHandler(self.network)
        self.start_hotkeys()
        
    def start_hotkeys(self):
        try:
            from human_typing import pynput_keyboard
            def on_press(key):
                if key == pynput_keyboard.Key.insert:
                    if self.pause_event.is_set():
                        self.pause_event.clear()
                        logging.info("Resumed via Insert key")
                    else:
                        self.pause_event.set()
                        logging.info("Paused via Insert key")
                elif key in [pynput_keyboard.Key.ctrl, pynput_keyboard.Key.ctrl_l, pynput_keyboard.Key.ctrl_r]:
                    self.cancel_event.set()
                    logging.info("Cancelled via Ctrl key")
            
            listener = pynput_keyboard.Listener(on_press=on_press)
            listener.daemon = True
            listener.start()
        except Exception as e:
            logging.warning(f"pynput not available, hotkeys disabled: {e}")
            
    def handle_server_message(self, message: dict):
        if not self.auto_control_enabled:
            logging.info("Auto control is disabled. Ignoring message.")
            return

        msg_type = message.get("type")
        data = message.get("data")
        
        if msg_type == "number":
            numbers = data if isinstance(data, list) else [data]
            
            if numbers:
                target_num = numbers[-1]
                
                self.cancel_event.clear()
                self.pause_event.clear()
                
                success, msg = led_controller.sweep_loop(target_num, self.cancel_event, self.pause_event)
                logging.info(f"LED action: {msg}. Waiting for 'Esc' key to acknowledge/cancel. 'Insert' to pause.")
                
                def wait_for_ack():
                    self.cancel_event.wait()
                    logging.info("Number acknowledged by user.")
                    self.network.send_feedback("success", "Number visually acknowledged by user.", "number")
                    
                threading.Thread(target=wait_for_ack, daemon=True).start()
                
        elif msg_type == "text":
            text_str = str(data)
            self.cancel_event.clear()
            self.pause_event.clear()
            
            def on_complete(status, feedback_msg):
                self.network.send_feedback(status, feedback_msg, "text")

            success, msg = typing_handler.type_text(
                text_str, 
                self.cancel_event, 
                self.pause_event, 
                on_complete
            )
            logging.info(f"Typing action: {msg}")
            
        elif msg_type == "command":
            # Handle specific commands from server if needed
            pass
        else:
            logging.warning(f"Unknown message type: {msg_type}")

    def cli_loop(self):
        print("--- LED & Typing Client ---")
        print("Commands: ")
        print("  auto on/off : Enable/disable automatic server control")
        print("  led <num>   : Manually set LED pattern (e.g., led 1 for CapsLock)")
        print("  exit        : Stop the client safely")
        
        while True:
            try:
                cmd_input = input("client> ").strip().lower()
                if not cmd_input:
                    continue
                    
                parts = cmd_input.split()
                cmd = parts[0]
                
                if cmd == "auto":
                    if len(parts) > 1:
                        if parts[1] == "on":
                            self.auto_control_enabled = True
                            print("Automatic server control enabled.")
                        elif parts[1] == "off":
                            self.auto_control_enabled = False
                            print("Automatic server control disabled.")
                    else:
                        print(f"Auto control is currently {'ON' if self.auto_control_enabled else 'OFF'}")
                
                elif cmd == "led":
                    if len(parts) > 1:
                        try:
                            num = int(parts[1])
                            success, msg = led_controller.indicate_pattern(num)
                            print(f"LED update: {msg}")
                        except ValueError:
                            print("Please provide a valid integer.")
                    else:
                        print("Usage: led <number>")
                        
                elif cmd == "exit" or cmd == "quit":
                    print("Shutting down client...")
                    self.network.disconnect()
                    break
                else:
                    print(f"Unknown command: {cmd}")
            except EOFError:
                break
            except Exception as e:
                print(f"Error in CLI: {e}")

    def run(self):
        self.network.connect()
        self.screenshot_handler.start()
        self.cli_loop()
        self.screenshot_handler.stop()

if __name__ == "__main__":
    app = Application()
    try:
        app.run()
    except KeyboardInterrupt:
        print("\nClient manually stopped.")
        app.network.disconnect()
