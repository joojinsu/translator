import tkinter as tk
from PIL import Image, ImageGrab
import ctypes
import os

def enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

def get_virtual_screen_geometry():
    enable_dpi_awareness()
    user32 = ctypes.windll.user32
    v_x = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
    v_y = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
    v_w = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
    v_h = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN

    if v_w <= 0 or v_h <= 0:
        v_w = user32.GetSystemMetrics(0)
        v_h = user32.GetSystemMetrics(1)
        v_x, v_y = 0, 0
    return v_x, v_y, v_w, v_h

def capture_screen_safe(v_x, v_y, v_w, v_h):
    # 1. Primary: ImageGrab with all_screens=True
    try:
        img = ImageGrab.grab(all_screens=True)
        if img:
            return img
    except Exception:
        pass

    # 2. Secondary: ImageGrab standard
    try:
        img = ImageGrab.grab()
        if img:
            return img
    except Exception:
        pass

    # 3. Tertiary: Windows ctypes GDI BitBlt
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        hdesktop = user32.GetDesktopWindow()
        desktop_dc = user32.GetWindowDC(hdesktop)
        img_dc = gdi32.CreateCompatibleDC(desktop_dc)
        mem_bitmap = gdi32.CreateCompatibleBitmap(desktop_dc, v_w, v_h)
        gdi32.SelectObject(img_dc, mem_bitmap)

        gdi32.BitBlt(img_dc, 0, 0, v_w, v_h, desktop_dc, v_x, v_y, 0x00CC0020)

        import struct
        bmpinfo = struct.pack('IiiHHIIiiII', 40, v_w, -v_h, 1, 32, 0, 0, 0, 0, 0, 0)
        buffer = ctypes.create_string_buffer(v_w * v_h * 4)
        gdi32.GetDIBits(img_dc, mem_bitmap, 0, v_h, buffer, bmpinfo, 0)

        img = Image.frombuffer('RGBA', (v_w, v_h), buffer, 'raw', 'BGRA', 0, 1).convert('RGB')

        gdi32.DeleteObject(mem_bitmap)
        gdi32.DeleteDC(img_dc)
        user32.ReleaseDC(hdesktop, desktop_dc)
        return img
    except Exception as e:
        print(f"[CaptureOverlay] GDI BitBlt error: {e}")
        return None

class CaptureOverlay:
    def __init__(self, on_capture_complete, on_cancel=None):
        self.on_capture_complete = on_capture_complete
        self.on_cancel = on_cancel
        self.start_x_root = None
        self.start_y_root = None
        self.start_cv_x = None
        self.start_cv_y = None
        self.rect_id = None
        self.dim_text_id = None
        self.full_screenshot = None
        self.overlay_window = None

    def start_capture(self):
        self.v_x, self.v_y, self.v_w, self.v_h = get_virtual_screen_geometry()
        self.full_screenshot = capture_screen_safe(self.v_x, self.v_y, self.v_w, self.v_h)
        if self.full_screenshot is None:
            if self.on_cancel:
                self.on_cancel("화면을 캡처할 수 없습니다.")
            return

        self.overlay_window = tk.Toplevel()
        # Cover all monitors across the virtual desktop
        self.overlay_window.overrideredirect(True)
        self.overlay_window.geometry(f"{self.v_w}x{self.v_h}+{self.v_x}+{self.v_y}")
        self.overlay_window.attributes("-topmost", True)
        self.overlay_window.attributes("-alpha", 0.35)
        self.overlay_window.config(cursor="cross")

        self.canvas = tk.Canvas(
            self.overlay_window,
            bg="#0f172a",
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        user32 = ctypes.windll.user32
        primary_w = user32.GetSystemMetrics(0)
        banner_w, banner_h = 440, 48
        # Center banner on primary monitor
        bx1 = -self.v_x + (primary_w - banner_w) // 2
        by1 = 40
        bx2 = bx1 + banner_w
        by2 = by1 + banner_h

        self.canvas.create_rectangle(
            bx1, by1, bx2, by2,
            fill="#1e293b",
            outline="#3b82f6",
            width=1.5
        )
        self.canvas.create_text(
            bx1 + banner_w // 2,
            by1 + banner_h // 2,
            text="✂ 번역할 영역을 마우스로 드래그하세요  |  취소: ESC",
            fill="#f8fafc",
            font=("Segoe UI", 12, "bold")
        )

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.overlay_window.bind("<Escape>", self.cancel_capture)

        self.overlay_window.focus_force()

    def on_button_press(self, event):
        self.start_x_root = event.x_root
        self.start_y_root = event.y_root
        self.start_cv_x = event.x
        self.start_cv_y = event.y

        self.rect_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#38bdf8",
            width=2,
            fill="#0284c7"
        )
        self.dim_text_id = self.canvas.create_text(
            event.x, event.y - 12,
            text="",
            fill="#ffffff",
            font=("Segoe UI", 10, "bold")
        )

    def on_move_press(self, event):
        if self.start_cv_x is None or self.start_cv_y is None:
            return

        cur_cv_x = event.x
        cur_cv_y = event.y

        self.canvas.coords(self.rect_id, self.start_cv_x, self.start_cv_y, cur_cv_x, cur_cv_y)

        w = abs(event.x_root - self.start_x_root)
        h = abs(event.y_root - self.start_y_root)
        min_x = min(self.start_cv_x, cur_cv_x)
        min_y = min(self.start_cv_y, cur_cv_y)
        self.canvas.coords(self.dim_text_id, min_x + 50, max(20, min_y - 12))
        self.canvas.itemconfig(self.dim_text_id, text=f"{w} × {h} px")

    def on_button_release(self, event):
        if not self.overlay_window or self.start_x_root is None or self.start_y_root is None:
            self.cancel_capture()
            return

        x1_root = min(self.start_x_root, event.x_root)
        y1_root = min(self.start_y_root, event.y_root)
        x2_root = max(self.start_x_root, event.x_root)
        y2_root = max(self.start_y_root, event.y_root)

        self.start_x_root = None
        self.start_y_root = None

        if self.overlay_window:
            try:
                self.overlay_window.destroy()
            except Exception:
                pass
            self.overlay_window = None

        if (x2_root - x1_root) < 10 or (y2_root - y1_root) < 10:
            if self.on_cancel:
                self.on_cancel("선택 영역이 너무 작습니다.")
            return

        if self.full_screenshot is None:
            if self.on_cancel:
                self.on_cancel("스크린샷 이미지가 없습니다.")
            return

        try:
            img_w, img_h = self.full_screenshot.size
            scale_x = img_w / self.v_w if self.v_w > 0 else 1.0
            scale_y = img_h / self.v_h if self.v_h > 0 else 1.0

            # Absolute virtual coordinates mapped to image pixels!
            crop_x1 = max(0, min(int((x1_root - self.v_x) * scale_x), img_w))
            crop_y1 = max(0, min(int((y1_root - self.v_y) * scale_y), img_h))
            crop_x2 = max(0, min(int((x2_root - self.v_x) * scale_x), img_w))
            crop_y2 = max(0, min(int((y2_root - self.v_y) * scale_y), img_h))

            if (crop_x2 - crop_x1) < 5 or (crop_y2 - crop_y1) < 5:
                if self.on_cancel:
                    self.on_cancel("영역을 다시 선택해 주세요.")
                return

            cropped = self.full_screenshot.crop((crop_x1, crop_y1, crop_x2, crop_y2))
            if self.on_capture_complete:
                w_root = x2_root - x1_root
                h_root = y2_root - y1_root
                self.on_capture_complete(cropped, (x1_root, y1_root, w_root, h_root))
        except Exception as e:
            print(f"[CaptureOverlay] Crop error: {e}")
            if self.on_cancel:
                self.on_cancel(f"영역 캡처 오류: {e}")

    def cancel_capture(self, event=None):
        self.start_x_root = None
        self.start_y_root = None
        if self.overlay_window:
            try:
                self.overlay_window.destroy()
            except Exception:
                pass
            self.overlay_window = None
        if self.on_cancel:
            self.on_cancel("캡처가 취소되었습니다.")
