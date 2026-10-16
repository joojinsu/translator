import customtkinter as ctk
from PIL import Image
import pyperclip

class ResultWindow:
    def __init__(self, parent, on_retranslate=None, on_recapture=None, always_on_top=True):
        self.parent = parent
        self.on_retranslate = on_retranslate
        self.on_recapture = on_recapture
        self.always_on_top = always_on_top
        self.window = None
        self.ctk_img = None

    def show_capture(self, cropped_image, target_lang="ko", source_lang="auto"):
        """
        Called IMMEDIATELY when mouse is released:
        Shows the captured image and loading state instantly!
        """
        if self.window and self.window.winfo_exists():
            self.window.destroy()

        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("스크린샷 번역")
        self.window.geometry("660x720")
        self.window.minsize(540, 560)
        self.window.attributes("-topmost", self.always_on_top)

        self.target_lang = target_lang
        self.source_lang = source_lang

        self._build_ui(cropped_image, target_lang, source_lang)
        self.window.focus_force()

    def _build_ui(self, cropped_image, target_lang, source_lang):
        main_box = ctk.CTkFrame(
            self.window,
            corner_radius=0,
            fg_color=("#f1f5f9", "#0f172a")
        )
        main_box.pack(fill="both", expand=True)

        self.inner = ctk.CTkScrollableFrame(
            main_box,
            fg_color="transparent",
            corner_radius=0
        )
        self.inner.pack(fill="both", expand=True, padx=20, pady=16)

        # 1. Top Bar: Badge, Toast, Always-on-top
        header_frame = ctk.CTkFrame(self.inner, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 10))

        badge = ctk.CTkLabel(
            header_frame,
            text=f"  🌐  {source_lang.upper()}  ➔  {target_lang.upper()}  ",
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            fg_color=("#2563eb", "#3b82f6"),
            text_color="#ffffff",
            corner_radius=12,
            height=30
        )
        badge.pack(side="left")

        self.toast_lbl = ctk.CTkLabel(
            header_frame,
            text="",
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            text_color="#10b981"
        )
        self.toast_lbl.pack(side="left", padx=12)

        self.pin_switch = ctk.CTkSwitch(
            header_frame,
            text="항상 위에 고정",
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            text_color=("#1e293b", "#e2e8f0"),
            command=self._toggle_always_on_top,
            switch_width=40,
            switch_height=22,
            progress_color=("#2563eb", "#3b82f6")
        )
        if self.always_on_top:
            self.pin_switch.select()
        else:
            self.pin_switch.deselect()
        self.pin_switch.pack(side="right")

        # 2. CAPTURED SCREEN PREVIEW CARD ("화면에 그 화면이 뜨면서")
        img_card = ctk.CTkFrame(
            self.inner,
            corner_radius=12,
            fg_color=("#ffffff", "#1e293b"),
            border_width=1,
            border_color=("#cbd5e1", "#334155")
        )
        img_card.pack(fill="x", pady=(0, 12))

        img_header = ctk.CTkFrame(img_card, fg_color="transparent")
        img_header.pack(fill="x", padx=12, pady=(8, 4))

        ctk.CTkLabel(
            img_header,
            text="📸 캡처된 화면 영역 (Selected Area)",
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            text_color=("#475569", "#94a3b8")
        ).pack(side="left")

        # Proportional resize for display
        max_w, max_h = 580, 180
        orig_w, orig_h = cropped_image.size
        scale = min(max_w / orig_w, max_h / orig_h, 1.0)
        disp_w = max(1, int(orig_w * scale))
        disp_h = max(1, int(orig_h * scale))

        self.ctk_img = ctk.CTkImage(
            light_image=cropped_image,
            dark_image=cropped_image,
            size=(disp_w, disp_h)
        )
        img_display = ctk.CTkLabel(
            img_card,
            text="",
            image=self.ctk_img,
            corner_radius=8
        )
        img_display.pack(padx=12, pady=(0, 10))

        # 3. Dynamic Section: Loading OR Results
        self.content_container = ctk.CTkFrame(self.inner, fg_color="transparent")
        self.content_container.pack(fill="both", expand=True)

        # Show initial loading card
        self._show_loading_ui()

        # 4. Action Buttons Footer
        footer_frame = ctk.CTkFrame(self.inner, fg_color="transparent")
        footer_frame.pack(fill="x", pady=(10, 0))

        if self.on_recapture:
            btn_recapture = ctk.CTkButton(
                footer_frame,
                text="📸 다시 캡처",
                font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
                width=110,
                height=38,
                corner_radius=10,
                fg_color=("#0ea5e9", "#0284c7"),
                text_color="#ffffff",
                hover_color=("#0284c7", "#0369a1"),
                command=self._handle_recapture
            )
            btn_recapture.pack(side="left", padx=(0, 10))

        btn_close = ctk.CTkButton(
            footer_frame,
            text="닫기 (ESC)",
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            width=95,
            height=38,
            corner_radius=10,
            fg_color=("#f1f5f9", "#1e293b"),
            border_width=1.5,
            border_color=("#94a3b8", "#475569"),
            text_color=("#334155", "#cbd5e1"),
            hover_color=("#e2e8f0", "#334155"),
            command=self.window.destroy
        )
        btn_close.pack(side="right")

        self.window.bind("<Escape>", lambda e: self.window.destroy())

    def _show_loading_ui(self):
        for widget in self.content_container.winfo_children():
            widget.destroy()

        load_card = ctk.CTkFrame(
            self.content_container,
            corner_radius=14,
            fg_color=("#ffffff", "#1e293b"),
            border_width=2,
            border_color=("#2563eb", "#3b82f6")
        )
        load_card.pack(fill="both", expand=True, pady=10)

        load_inner = ctk.CTkFrame(load_card, fg_color="transparent")
        load_inner.pack(fill="both", expand=True, padx=20, pady=30)

        self.loading_bar = ctk.CTkProgressBar(
            load_inner,
            height=6,
            corner_radius=3,
            progress_color=("#2563eb", "#3b82f6")
        )
        self.loading_bar.pack(fill="x", pady=(0, 16))
        self.loading_bar.start()

        ctk.CTkLabel(
            load_inner,
            text="🔍 EasyOCR 텍스트 인식 및 번역 중...",
            font=ctk.CTkFont(family="Malgun Gothic", size=16, weight="bold"),
            text_color=("#1d4ed8", "#60a5fa")
        ).pack(pady=(0, 6))

        ctk.CTkLabel(
            load_inner,
            text="잠시만 기다려 주세요 (약 1초 소요)",
            font=ctk.CTkFont(family="Malgun Gothic", size=12),
            text_color=("#64748b", "#94a3b8")
        ).pack()

    def update_result(self, original_text, translated_text):
        """
        Called when OCR and Translation finish: replaces loading card with result cards!
        """
        if not self.window or not self.window.winfo_exists():
            return

        for widget in self.content_container.winfo_children():
            widget.destroy()

        # 1. HERO: Translation Card
        trans_card = ctk.CTkFrame(
            self.content_container,
            corner_radius=14,
            fg_color=("#ffffff", "#1e293b"),
            border_width=2,
            border_color=("#2563eb", "#3b82f6")
        )
        trans_card.pack(fill="both", expand=True, pady=(0, 12))

        trans_header = ctk.CTkFrame(trans_card, fg_color="transparent")
        trans_header.pack(fill="x", padx=14, pady=(12, 6))

        ctk.CTkLabel(
            trans_header,
            text="✨ 한국어 번역 결과",
            font=ctk.CTkFont(family="Malgun Gothic", size=15, weight="bold"),
            text_color=("#1d4ed8", "#60a5fa")
        ).pack(side="left")

        self.btn_copy_trans = ctk.CTkButton(
            trans_header,
            text="📋 번역 복사",
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            width=95,
            height=30,
            corner_radius=8,
            fg_color=("#2563eb", "#3b82f6"),
            text_color="#ffffff",
            hover_color=("#1d4ed8", "#2563eb"),
            command=self._copy_translation
        )
        self.btn_copy_trans.pack(side="right")

        self.trans_textbox = ctk.CTkTextbox(
            trans_card,
            font=ctk.CTkFont(family="Malgun Gothic", size=15, weight="bold"),
            text_color=("#0f172a", "#f8fafc"),
            fg_color=("#f8fafc", "#0f172a"),
            corner_radius=10,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
            wrap="word",
            height=130
        )
        self.trans_textbox.insert("1.0", translated_text)
        self.trans_textbox.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        try:
            self.trans_textbox._textbox.configure(spacing1=3, spacing2=5, spacing3=3)
        except Exception:
            pass

        # 2. Original OCR Text Card
        orig_card = ctk.CTkFrame(
            self.content_container,
            corner_radius=12,
            fg_color=("#ffffff", "#1e293b"),
            border_width=1,
            border_color=("#cbd5e1", "#334155")
        )
        orig_card.pack(fill="both", expand=True, pady=(0, 10))

        orig_header = ctk.CTkFrame(orig_card, fg_color="transparent")
        orig_header.pack(fill="x", padx=14, pady=(10, 4))

        ctk.CTkLabel(
            orig_header,
            text="📝 인식된 원문 (English Text)",
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            text_color=("#475569", "#94a3b8")
        ).pack(side="left")

        btn_row = ctk.CTkFrame(orig_header, fg_color="transparent")
        btn_row.pack(side="right")

        if self.on_retranslate:
            btn_retrans = ctk.CTkButton(
                btn_row,
                text="🔄 수정 후 다시 번역",
                font=ctk.CTkFont(family="Malgun Gothic", size=11, weight="bold"),
                width=115,
                height=26,
                corner_radius=6,
                fg_color=("#f1f5f9", "#334155"),
                text_color=("#0f172a", "#f8fafc"),
                hover_color=("#e2e8f0", "#475569"),
                command=self._handle_retranslate
            )
            btn_retrans.pack(side="left", padx=(0, 6))

        self.btn_copy_orig = ctk.CTkButton(
            btn_row,
            text="📋 원문 복사",
            font=ctk.CTkFont(family="Malgun Gothic", size=11, weight="bold"),
            width=80,
            height=26,
            corner_radius=6,
            fg_color=("#e2e8f0", "#334155"),
            text_color=("#1e293b", "#f8fafc"),
            hover_color=("#cbd5e1", "#475569"),
            command=self._copy_original
        )
        self.btn_copy_orig.pack(side="left")

        self.orig_textbox = ctk.CTkTextbox(
            orig_card,
            font=ctk.CTkFont(family="Malgun Gothic", size=13),
            text_color=("#1e293b", "#e2e8f0"),
            fg_color=("#f8fafc", "#0f172a"),
            corner_radius=8,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
            wrap="word",
            height=90
        )
        self.orig_textbox.insert("1.0", original_text)
        self.orig_textbox.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        try:
            self.orig_textbox._textbox.configure(spacing1=2, spacing2=4, spacing3=2)
        except Exception:
            pass

    def show_error(self, err_msg):
        if not self.window or not self.window.winfo_exists():
            return

        for widget in self.content_container.winfo_children():
            widget.destroy()

        err_card = ctk.CTkFrame(
            self.content_container,
            corner_radius=14,
            fg_color=("#ffffff", "#1e293b"),
            border_width=2,
            border_color="#ef4444"
        )
        err_card.pack(fill="both", expand=True, pady=10)

        err_inner = ctk.CTkFrame(err_card, fg_color="transparent")
        err_inner.pack(fill="both", expand=True, padx=20, pady=24)

        ctk.CTkLabel(
            err_inner,
            text="⚠️ 텍스트 인식 / 번역 안내",
            font=ctk.CTkFont(family="Malgun Gothic", size=16, weight="bold"),
            text_color="#ef4444"
        ).pack(pady=(0, 8))

        ctk.CTkLabel(
            err_inner,
            text=f"{err_msg}\n\n글자가 선명하지 않거나 너무 작을 수 있습니다.\n화면을 조금 더 넓게 캡처해 보세요.",
            font=ctk.CTkFont(family="Malgun Gothic", size=13),
            text_color=("#334155", "#cbd5e1"),
            justify="center"
        ).pack(pady=(0, 14))

        if self.on_recapture:
            ctk.CTkButton(
                err_inner,
                text="📸 다시 캡처하기",
                font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
                width=130,
                height=36,
                corner_radius=8,
                fg_color=("#2563eb", "#3b82f6"),
                command=self._handle_recapture
            ).pack()

    def _toggle_always_on_top(self):
        self.always_on_top = bool(self.pin_switch.get())
        if self.window:
            self.window.attributes("-topmost", self.always_on_top)

    def _copy_translation(self):
        text = self.trans_textbox.get("1.0", "end-1c").strip()
        if text:
            pyperclip.copy(text)
            self._show_toast("✓ 번역 결과가 클립보드에 복사되었습니다!")
            self.btn_copy_trans.configure(text="✓ 복사됨!", fg_color="#10b981")
            self.window.after(2000, lambda: self.btn_copy_trans.configure(text="📋 번역 복사", fg_color=("#2563eb", "#3b82f6")))

    def _copy_original(self):
        text = self.orig_textbox.get("1.0", "end-1c").strip()
        if text:
            pyperclip.copy(text)
            self._show_toast("✓ 원문이 클립보드에 복사되었습니다!")
            self.btn_copy_orig.configure(text="✓ 복사됨!")
            self.window.after(2000, lambda: self.btn_copy_orig.configure(text="📋 원문 복사"))

    def _show_toast(self, message):
        self.toast_lbl.configure(text=message)
        self.window.after(2500, lambda: self.toast_lbl.configure(text=""))

    def _handle_recapture(self):
        if self.window:
            self.window.destroy()
        if self.on_recapture:
            self.on_recapture()

    def _handle_retranslate(self):
        edited_text = self.orig_textbox.get("1.0", "end-1c").strip()
        if not edited_text:
            return
        if self.on_retranslate:
            self._show_toast("🔄 번역 중...")
            new_translation = self.on_retranslate(edited_text)
            self.trans_textbox.delete("1.0", "end")
            self.trans_textbox.insert("1.0", new_translation)
            self._show_toast("✓ 번역 갱신 완료!")
