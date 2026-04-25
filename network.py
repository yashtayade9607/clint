import asyncio
import json
import threading
import time
import logging
import aiohttp

class TCPClient:
    """
    Renamed to TCPClient for backward compatibility with client.py, 
    but now uses WebSockets for Railway compatibility.
    """
    def __init__(self, host='led-server-production-5f97.up.railway.app', port=8888, on_message=None, pause_event=None):
        # We use the HTTPS URL for Railway
        if "up.railway.app" in host:
            self.url = f"wss://{host.replace('https://', '').replace('http://', '')}/ws"
        else:
            self.url = f"ws://{host.replace('https://', '').replace('http://', '')}:{port}/ws"
            
        self.ws = None
        self.is_connected = False
        self.should_run = True
        self.on_message = on_message
        self.pause_event = pause_event
        self.network_thread = None
        self.reconnect_delay = 2
        self.loop = None

    def connect(self):
        self.should_run = True
        self.network_thread = threading.Thread(target=self._start_loop, daemon=True)
        self.network_thread.start()

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
                            self.ws = ws
                            self.is_connected = True
                            self.reconnect_delay = 2
                            logging.info(f"Connected to server via WebSocket: {self.url}")
                            
                            # Handshake: Not ready yet
                            await self._send_message_async({"type": "status", "ready": False})
                            
                            # Trigger acknowledgement blink
                            self._trigger_acknowledgement()
                            
                            async for msg in ws:
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    if self.on_message:
                                        try:
                                            data = json.loads(msg.data)
                                            self.on_message(data)
                                        except Exception as e:
                                            logging.error(f"Error processing message: {e}")
                                elif msg.type == aiohttp.WSMsgType.CLOSED:
                                    break
                                elif msg.type == aiohttp.WSMsgType.ERROR:
                                    break
                            
                            self.is_connected = False
                except Exception as e:
                    logging.error(f"WebSocket connection failed: {e}. Retrying in {self.reconnect_delay}s...")
                    self.is_connected = False
                    await asyncio.sleep(self.reconnect_delay)
                    self.reconnect_delay = min(self.reconnect_delay * 2, 30)
            else:
                await asyncio.sleep(1)

    def _trigger_acknowledgement(self):
        from led_controller import led_controller
        from pynput import keyboard as _kb
        connect_stop = threading.Event()
        led_controller.blink_all_until_stopped(connect_stop, pause_event=self.pause_event)
        logging.info("Connection established. Press Ctrl to acknowledge (stop LED blink).")
        
        def _wait_ack():
            def _on_press(key):
                if key in [_kb.Key.ctrl, _kb.Key.ctrl_l, _kb.Key.ctrl_r]:
                    connect_stop.set()
                    return False
            with _kb.Listener(on_press=_on_press) as lst:
                lst.join()
            # Esc pressed — tell server we are now ready (CTS)
            self.send_message({"type": "status", "ready": True})
            logging.info("CTS sent to server. Ready to receive commands.")
            
        threading.Thread(target=_wait_ack, daemon=True).start()

    def send_message(self, message: dict):
        """Synchronous wrapper to send messages via the async WebSocket loop."""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._send_message_async(message), self.loop)
            return True
        return False

    async def _send_message_async(self, message: dict):
        if self.ws and not self.ws.closed:
            try:
                await self.ws.send_json(message)
                return True
            except Exception as e:
                logging.error(f"Failed to send WebSocket message: {e}")
                return False
        return False

    def send_feedback(self, status: str, message: str, original_action: str = "unknown"):
        msg = {
            "type": "feedback",
            "status": status,
            "message": message,
            "action": original_action
        }
        return self.send_message(msg)

    def disconnect(self):
        self.should_run = False
        if self.loop:
            # We can't easily stop the loop from another thread gracefully 
            # without more complexity, but setting should_run=False will stop the while loop.
            pass
        self.is_connected = False
