import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk
import pyperclip

class ScreenOverlayTranslator:
    """
    Layout-Preserving In-Place Screen Translator.
    Displays translated text directly over the original screen layout:
    - Headings stay where headings were.
    - Bullet points stay where bullet points were.
    - Word wrapping prevents any text overlapping or clipping.
    - Spacebar toggles between original English screen and translated Korean screen.
    - Hovering over any section shows a clear subtitle mapping the original to translation.
    - Uses tk.Toplevel for 100% pixel-perfect coordinate alignment across all DPI scalings.
    """
    def __init__(self, parent, on_recapture=None, on_open_details=None):
        self.parent = parent
        self.on_recapture = on_recapture
        self.on_open_details = on_open_details

        self.window = None
        self.canvas = None
        self.loading_window_id = None
        self.tooltip_window_id = None

        self.screen_x = 0
        self.screen_y = 0
        self.width = 0
        self.height = 0

        self.orig_pil = None
        self.trans_pil = None
        self.orig_photo = None
        self.trans_photo = None

        self.blocks = []
        self.full_orig = ""
        self.full_trans = ""
        self.showing_orig = False

        self._drag_start_x = 0
        self._drag_start_y = 0

    def show_at(self, screen_x, screen_y, width, height, orig_pil_img, is_loading=True):
        if self.window and self.window.winfo_exists():
            self.window.destroy()

        self.screen_x = screen_x
        self.screen_y = screen_y
        self.width = max(width, 100)
        self.height = max(height, 50)
        self.orig_pil = orig_pil_img
        self.trans_pil = None
        self.blocks = []
        self.full_orig = ""
        self.full_trans = ""
        self.showing_orig = False

        # Use standard tk.Toplevel to avoid CTkToplevel internal DPI scaling coordinate offsets
        self.window = tk.Toplevel(self.parent)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.geometry(f"{self.width}x{self.height}+{self.screen_x}+{self.screen_y}")

        # Hotkeys
        self.window.bind("<Escape>", lambda e: self.close())
        self.window.bind("<space>", lambda e: self._toggle_view())
        self.window.bind("<Control-c>", lambda e: self._copy_translation())
        self.window.bind("<Double-Button-1>", lambda e: self.close())

        # Main Canvas covering the exact captured region
        self.canvas = tk.Canvas(
            self.window,
            width=self.width,
            height=self.height,
            bd=0,
            highlightthickness=0,
            cursor="arrow"
        )
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-3>", self._start_drag)
        self.canvas.bind("<B3-Motion>", self._do_drag)
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<Leave>", self._on_mouse_leave)

        # Display initial screenshot
        disp_orig = self.orig_pil.resize((self.width, self.height), Image.Resampling.LANCZOS)
        self.orig_photo = ImageTk.PhotoImage(disp_orig)
        self.canvas_img_id = self.canvas.create_image(0, 0, anchor="nw", image=self.orig_photo)

        if is_loading:
            self._show_loading_badge()

        self._build_floating_toolbar()
        self.window.focus_force()

    def _show_loading_badge(self):
        self.loading_frame = ctk.CTkFrame(
            self.canvas,
            fg_color="#0f172a",
            border_width=2,
            border_color="#3b82f6",
            corner_radius=16,
            height=34
        )
        lbl = ctk.CTkLabel(
            self.loading_frame,
            text="⚡ 원문 레이아웃에 맞춰 자연스러운 한국어로 번역 중...",
            font=ctk.CTkFont(family="Malgun Gothic", size=11, weight="bold"),
            text_color="#60a5fa"
        )
        lbl.pack(side="left", padx=14, pady=5)

        cx = self.width // 2
        cy = max(24, self.height // 2)
        self.loading_window_id = self.canvas.create_window(cx, cy, window=self.loading_frame)

    def _hide_loading_badge(self):
        if self.loading_window_id:
            try:
                self.canvas.delete(self.loading_window_id)
            except Exception:
                pass
            self.loading_window_id = None

    def update_in_place_result(self, orig_pil_img, trans_pil_img, blocks, full_orig, full_trans):
        """
        Called when In-Place Layout Translation finishes.
        Updates the canvas with the translated image where English text is cleanly replaced
        in-place by Korean text matching the original headings and bullet points!
        """
        if not self.window or not self.window.winfo_exists():
            return

        self._hide_loading_badge()

        self.orig_pil = orig_pil_img
        self.trans_pil = trans_pil_img
        self.blocks = blocks
        self.full_orig = full_orig.strip()
        self.full_trans = full_trans.strip()
        self.showing_orig = False

        # Scale images to overlay dimensions
        disp_orig = self.orig_pil.resize((self.width, self.height), Image.Resampling.LANCZOS)
        disp_trans = self.trans_pil.resize((self.width, self.height), Image.Resampling.LANCZOS)
        self.orig_photo = ImageTk.PhotoImage(disp_orig)
        self.trans_photo = ImageTk.PhotoImage(disp_trans)

        # Show translated in-place image!
        self.canvas.itemconfig(self.canvas_img_id, image=self.trans_photo)
        self._update_toolbar_state()

    def show_error(self, err_msg):
        if not self.window or not self.window.winfo_exists():
            return
        self._hide_loading_badge()

        err_frame = ctk.CTkFrame(
            self.canvas,
            fg_color="#450a0a",
            border_width=2,
            border_color="#ef4444",
            corner_radius=12
        )
        ctk.CTkLabel(
            err_frame,
            text=f"⚠️ {err_msg}",
            font=ctk.CTkFont(family="Malgun Gothic", size=11, weight="bold"),
            text_color="#fca5a5"
        ).pack(padx=14, pady=6)

        cx = self.width // 2
        cy = max(24, self.height // 2)
        self.canvas.create_window(cx, cy, window=err_frame)

    def _build_floating_toolbar(self):
        self.toolbar = ctk.CTkFrame(
            self.canvas,
            fg_color="#0f172a",
            border_width=1,
            border_color="#334155",
            corner_radius=14,
            height=28
        )

        # Drag handle
        drag_handle = ctk.CTkLabel(
            self.toolbar,
            text="⠿",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#64748b",
            cursor="fleur",
            width=16
        )
        drag_handle.pack(side="left", padx=(6, 2), pady=2)
        drag_handle.bind("<ButtonPress-1>", self._start_drag)
        drag_handle.bind("<B1-Motion>", self._do_drag)
        self.toolbar.bind("<ButtonPress-1>", self._start_drag)
        self.toolbar.bind("<B1-Motion>", self._do_drag)

        # Toggle Original / Translated
        self.btn_toggle = ctk.CTkButton(
            self.toolbar,
            text="👁 원문 (Space)",
            font=ctk.CTkFont(family="Malgun Gothic", size=10, weight="bold"),
            width=80,
            height=22,
            corner_radius=10,
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#94a3b8",
            command=self._toggle_view
        )
        self.btn_toggle.pack(side="left", padx=2, pady=3)

        # Copy button
        self.btn_copy = ctk.CTkButton(
            self.toolbar,
            text="📋 복사",
            font=ctk.CTkFont(family="Malgun Gothic", size=10, weight="bold"),
            width=48,
            height=22,
            corner_radius=10,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            text_color="#ffffff",
            command=self._copy_translation
        )
        self.btn_copy.pack(side="left", padx=2, pady=3)

        # Detailed window button
        if self.on_open_details:
            btn_details = ctk.CTkButton(
                self.toolbar,
                text="↗ 텍스트창",
                font=ctk.CTkFont(family="Malgun Gothic", size=10, weight="bold"),
                width=58,
                height=22,
                corner_radius=10,
                fg_color="#334155",
                hover_color="#475569",
                text_color="#cbd5e1",
                command=self._open_details
            )
            btn_details.pack(side="left", padx=2, pady=3)

        # Close button
        btn_close = ctk.CTkButton(
            self.toolbar,
            text="✕",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            width=24,
            height=22,
            corner_radius=11,
            fg_color="transparent",
            hover_color="#ef4444",
            text_color="#cbd5e1",
            command=self.close
        )
        btn_close.pack(side="left", padx=(2, 8), pady=3)

        # Pin toolbar to the top-right corner of the overlay canvas with an 8px margin.
        # Using anchor="ne" locks the North-East corner at (self.width - 8, 8),
        # ensuring the close button (✕) on the right edge is never clipped or pushed outside the window.
        tb_x = self.width - 8
        tb_y = 8

        self.toolbar_window_id = self.canvas.create_window(tb_x, tb_y, window=self.toolbar, anchor="ne")

    def _toggle_view(self):
        if not self.trans_photo:
            return
        self.showing_orig = not self.showing_orig
        if self.showing_orig:
            self.canvas.itemconfig(self.canvas_img_id, image=self.orig_photo)
            self.btn_toggle.configure(text="🌐 번역 보기 (Space)", fg_color="#3b82f6", text_color="#ffffff")
        else:
            self.canvas.itemconfig(self.canvas_img_id, image=self.trans_photo)
            self.btn_toggle.configure(text="👁 원문 (Space)", fg_color="#1e293b", text_color="#94a3b8")

    def _update_toolbar_state(self):
        if not hasattr(self, 'btn_toggle'):
            return
        if self.showing_orig:
            self.btn_toggle.configure(text="🌐 번역 보기 (Space)", fg_color="#3b82f6", text_color="#ffffff")
        else:
            self.btn_toggle.configure(text="👁 원문 (Space)", fg_color="#1e293b", text_color="#94a3b8")

    def _copy_translation(self):
        text = self.full_orig if self.showing_orig else self.full_trans
        if text:
            pyperclip.copy(text)
            self.btn_copy.configure(text="✓ 완료", fg_color="#10b981")
            self.window.after(1500, lambda: self.btn_copy.configure(text="📋 복사", fg_color="#2563eb"))

    def _open_details(self):
        self.close()
        if self.on_open_details:
            self.on_open_details(self.full_orig, self.full_trans)

    def _on_mouse_move(self, event):
        """Shows floating subtitle comparison tooltip on hover over any section."""
        if not self.blocks or not self.orig_pil:
            return

        scale_x = self.width / self.orig_pil.width
        scale_y = self.height / self.orig_pil.height

        mx = event.x
        my = event.y

        matched = None
        for blk in self.blocks:
            bx1, by1, bx2, by2 = blk['box']
            if bx1 * scale_x <= mx <= bx2 * scale_x and by1 * scale_y <= my <= by2 * scale_y:
                matched = blk
                break

        if matched:
            self._show_comparison_tooltip(matched['text'], matched.get('trans_text', ''), mx, my)
        else:
            self._hide_comparison_tooltip()

    def _show_comparison_tooltip(self, orig_text, trans_text, mx, my):
        self._hide_comparison_tooltip()

        self.tip_frame = ctk.CTkFrame(
            self.canvas,
            fg_color="#090d16",
            border_width=1,
            border_color="#38bdf8",
            corner_radius=8
        )
        orig_disp = orig_text if len(orig_text) <= 60 else orig_text[:57] + "..."
        trans_disp = trans_text if len(trans_text) <= 60 else trans_text[:57] + "..."
        txt = f"🔤 {orig_disp}\n➔ 🌐 {trans_disp}"
        ctk.CTkLabel(
            self.tip_frame,
            text=txt,
            font=ctk.CTkFont(family="Malgun Gothic", size=10, weight="bold"),
            text_color="#f8fafc",
            justify="left"
        ).pack(padx=8, pady=4)

        tx = max(110, min(self.width - 110, mx))
        ty = min(self.height - 28, my + 32)
        self.tooltip_window_id = self.canvas.create_window(tx, ty, window=self.tip_frame)

    def _hide_comparison_tooltip(self):
        if self.tooltip_window_id:
            try:
                self.canvas.delete(self.tooltip_window_id)
            except Exception:
                pass
            self.tooltip_window_id = None

    def _on_mouse_leave(self, event):
        self._hide_comparison_tooltip()

    def _start_drag(self, event):
        self._drag_start_x = event.x_root - self.window.winfo_x()
        self._drag_start_y = event.y_root - self.window.winfo_y()

    def _do_drag(self, event):
        new_x = event.x_root - self._drag_start_x
        new_y = event.y_root - self._drag_start_y
        self.window.geometry(f"+{new_x}+{new_y}")

    def close(self):
        if self.window and self.window.winfo_exists():
            self.window.destroy()
            self.window = None
