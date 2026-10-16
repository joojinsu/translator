import threading
import pystray
from PIL import Image, ImageDraw, ImageFont

def create_tray_image():
    """Generates a modern, clean 64x64 icon for the system tray."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded background with smooth blue gradient color
    draw.rounded_rectangle([3, 3, 61, 61], radius=14, fill=(37, 99, 235), outline=(96, 165, 250), width=2)

    # Draw stylish 'T' / translation mark
    try:
        font = ImageFont.truetype("C:\\Windows\\Fonts\\segoeui.ttf", 36)
    except Exception:
        font = ImageFont.load_default()

    # Center the letter 'T'
    bbox = draw.textbbox((0, 0), "T", font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (64 - tw) // 2
    ty = (64 - th) // 2 - 2
    draw.text((tx, ty), "T", fill=(255, 255, 255), font=font)

    # Add a small dot badge at bottom right
    draw.ellipse([44, 44, 56, 56], fill=(16, 185, 129), outline=(255, 255, 255), width=2)

    return img

class TrayManager:
    def __init__(self, on_show=None, on_capture=None, on_exit=None):
        self.on_show = on_show
        self.on_capture = on_capture
        self.on_exit = on_exit
        self.icon = None
        self._thread = None
        self.has_shown_hint = False

    def start(self):
        if self.icon is not None:
            return

        image = create_tray_image()
        menu = pystray.Menu(
            pystray.MenuItem("🖥️ 메인 창 열기", self._handle_show, default=True),
            pystray.MenuItem("📷 캡처 및 번역 (Ctrl+Alt+T)", self._handle_capture),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ 프로그램 완전히 종료", self._handle_exit)
        )

        self.icon = pystray.Icon(
            "EasyOCR_Translator",
            image,
            "EasyOCR 스크린샷 번역기 (백그라운드 실행 중)",
            menu
        )

        self._thread = threading.Thread(target=self.icon.run, daemon=True)
        self._thread.start()

    def _handle_show(self, icon=None, item=None):
        if self.on_show:
            self.on_show()

    def _handle_capture(self, icon=None, item=None):
        if self.on_capture:
            self.on_capture()

    def _handle_exit(self, icon=None, item=None):
        self.stop()
        if self.on_exit:
            self.on_exit()

    def notify(self, title, message):
        """Displays a Windows tray toast notification."""
        if self.icon:
            try:
                self.icon.notify(message, title)
            except Exception as e:
                print(f"[TrayManager] Notification error: {e}")

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None
