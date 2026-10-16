import threading
import time
from PIL import ImageGrab, Image
import io

class HotkeyManager:
    def __init__(self, on_hotkey_triggered, on_clipboard_image=None):
        self.on_hotkey_triggered = on_hotkey_triggered
        self.on_clipboard_image = on_clipboard_image
        self.hotkey_listener = None
        self.clipboard_thread = None
        self.is_monitoring_clipboard = False
        self.last_clipboard_hash = None
        self.hotkey_str = "<ctrl>+<alt>+t"
        self._last_trigger_time = 0.0

    def start_hotkey(self, hotkey_str="<ctrl>+<alt>+t"):
        self.stop_hotkey()
        self.hotkey_str = hotkey_str
        try:
            from pynput import keyboard
            # Format hotkey string for pynput
            hotkey_mapping = {self.hotkey_str: self._on_hotkey}
            self.hotkey_listener = keyboard.GlobalHotKeys(hotkey_mapping)
            self.hotkey_listener.daemon = True
            self.hotkey_listener.start()
            print(f"[HotkeyManager] Global hotkey registered: {self.hotkey_str}")
            return True
        except Exception as e:
            print(f"[HotkeyManager] Failed to register global hotkey: {e}")
            return False

    def _on_hotkey(self):
        now = time.time()
        # Debounce: prevent multiple triggers from typematic repeat or modifier oscillation
        if now - getattr(self, "_last_trigger_time", 0.0) < 0.8:
            return
        self._last_trigger_time = now
        print("[HotkeyManager] Hotkey triggered!")
        if self.on_hotkey_triggered:
            self.on_hotkey_triggered()

    def stop_hotkey(self):
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except Exception:
                pass
            self.hotkey_listener = None

    def start_clipboard_monitor(self):
        if self.is_monitoring_clipboard:
            return
        self.is_monitoring_clipboard = True
        self.clipboard_thread = threading.Thread(target=self._monitor_clipboard_loop, daemon=True)
        self.clipboard_thread.start()
        print("[HotkeyManager] Clipboard monitor started.")

    def stop_clipboard_monitor(self):
        self.is_monitoring_clipboard = False

    def _monitor_clipboard_loop(self):
        while self.is_monitoring_clipboard:
            try:
                img = ImageGrab.grabclipboard()
                if isinstance(img, Image.Image):
                    # Compute quick hash or signature of image to detect if it's new
                    img_bytes = img.tobytes()
                    img_hash = hash(img_bytes[:10000]) if len(img_bytes) > 10000 else hash(img_bytes)
                    
                    if self.last_clipboard_hash is None:
                        # Initial state: just store hash without triggering immediately
                        self.last_clipboard_hash = img_hash
                    elif img_hash != self.last_clipboard_hash:
                        self.last_clipboard_hash = img_hash
                        print("[HotkeyManager] New image detected in clipboard!")
                        if self.on_clipboard_image:
                            self.on_clipboard_image(img)
            except Exception as e:
                pass
            time.sleep(0.8)

    def cleanup(self):
        self.stop_hotkey()
        self.stop_clipboard_monitor()
