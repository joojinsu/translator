import sys
import os
import ctypes
import threading
import queue
import traceback
import customtkinter as ctk
from PIL import Image

import config as cfg
from ocr_engine import OCREngine
from translator_engine import TranslatorEngine
from capture_overlay import CaptureOverlay, enable_dpi_awareness
from hotkey_manager import HotkeyManager
from result_window import ResultWindow
from screen_overlay import ScreenOverlayTranslator
from ar_render_engine import group_ocr_into_blocks, render_in_place_translation
from tray_manager import TrayManager

# Appearance settings
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

LANGUAGES = {
    "한국어 (Korean)": "ko",
    "영어 (English)": "en",
    "일본어 (Japanese)": "ja",
    "중국어 간체 (Chinese)": "zh-CN",
    "중국어 번체 (Trad Chinese)": "zh-TW",
    "스페인어 (Spanish)": "es",
    "프랑스어 (French)": "fr",
    "독일어 (German)": "de",
    "러시아어 (Russian)": "ru",
    "베트남어 (Vietnamese)": "vi"
}

SOURCE_LANGUAGES = {
    "🌐 자동 감지 (Auto)": "auto",
    **LANGUAGES
}

OCR_LANG_PRESETS = {
    "한국어 + 영어 (권장)": ["ko", "en"],
    "영어 전용 (English)": ["en"],
    "일본어 + 영어": ["ja", "en"],
    "중국어 간체 + 영어": ["ch_sim", "en"],
    "중국어 번체 + 영어": ["ch_tra", "en"]
}

HOTKEY_PRESETS = {
    "Ctrl + Alt + T": "<ctrl>+<alt>+t",
    "Ctrl + Shift + S": "<ctrl>+<shift>+s",
    "F9": "<f9>",
    "F10": "<f10>",
    "Alt + Q": "<alt>+q",
    "Ctrl + Alt + Z": "<ctrl>+<alt>+z"
}

class ModernTranslatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("EasyOCR 스크린샷 자동 번역기")
        self.root.geometry("660x700")
        self.root.minsize(580, 620)

        enable_dpi_awareness()

        self.settings = cfg.load_config()
        self.ui_queue = queue.Queue()
        self.last_captured_img = None
        self.last_bbox = None
        self.is_capturing = False

        # Engine init
        self.ocr_engine = OCREngine(languages=self.settings.get("ocr_languages", ["ko", "en"]))
        self.translator = TranslatorEngine(
            target_lang=self.settings.get("target_lang", "ko"),
            source_lang=self.settings.get("source_lang", "auto")
        )

        # In-Place Screen Overlay Translator (Translates directly on top of the screen!)
        self.screen_overlay = ScreenOverlayTranslator(
            self.root,
            on_recapture=self.start_capture,
            on_open_details=self.open_detailed_result
        )

        # Full Detailed Result Window
        self.result_window = ResultWindow(
            self.root,
            on_retranslate=self.retranslate_text,
            on_recapture=self.start_capture,
            always_on_top=self.settings.get("always_on_top", True)
        )

        self._build_ui()

        # Start OCR loading in background
        self.progress_bar.start()
        self.status_lbl.configure(text="EasyOCR 딥러닝 모델 로딩 중...", text_color=("#d97706", "#f59e0b"))
        self.ocr_engine.initialize_async(self.on_ocr_initialized)

        # Global Hotkey Manager
        self.hotkey_mgr = HotkeyManager(
            on_hotkey_triggered=self.on_hotkey_triggered,
            on_clipboard_image=self.on_clipboard_image_detected
        )
        self._setup_hotkey()

        # System Tray Manager for Background Persistence
        self.tray_mgr = TrayManager(
            on_show=lambda: self.root.after(0, self.show_main_window),
            on_capture=lambda: self.root.after(0, self.start_capture),
            on_exit=lambda: self.root.after(0, self.quit_app)
        )
        self.tray_mgr.start()

        # Event loop timer
        self.root.after(100, self._process_ui_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        if self.settings.get("start_minimized", False):
            self.root.withdraw()

    def _build_ui(self):
        container = ctk.CTkFrame(
            self.root,
            corner_radius=0,
            fg_color=("#f1f5f9", "#0f172a")
        )
        container.pack(fill="both", expand=True, padx=0, pady=0)

        inner = ctk.CTkFrame(container, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=24, pady=20)

        # 1. Header (Title + Theme selector)
        header = ctk.CTkFrame(inner, fg_color="transparent")
        header.pack(fill="x", pady=(0, 16))

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left")

        title = ctk.CTkLabel(
            title_box,
            text="📸 EasyOCR 스냅 번역",
            font=ctk.CTkFont(family="Malgun Gothic", size=22, weight="bold"),
            text_color=("#0f172a", "#f8fafc")
        )
        title.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            title_box,
            text="단축키를 누르면 화면을 캡처하여 즉시 텍스트를 추출하고 번역합니다.",
            font=ctk.CTkFont(family="Malgun Gothic", size=12),
            text_color=("#475569", "#94a3b8")
        )
        subtitle.pack(anchor="w", pady=(2, 0))

        self.theme_segmented = ctk.CTkSegmentedButton(
            header,
            values=["System", "Dark", "Light"],
            font=ctk.CTkFont(family="Malgun Gothic", size=11, weight="bold"),
            width=160,
            height=32,
            corner_radius=8,
            command=self._change_theme
        )
        self.theme_segmented.set("System")
        self.theme_segmented.pack(side="right", pady=4)

        # 2. Main Hero Action Card
        hero_card = ctk.CTkFrame(
            inner,
            corner_radius=16,
            fg_color=("#ffffff", "#1e293b"),
            border_width=2,
            border_color=("#2563eb", "#3b82f6")
        )
        hero_card.pack(fill="x", pady=(0, 16), ipady=4)

        hero_inner = ctk.CTkFrame(hero_card, fg_color="transparent")
        hero_inner.pack(fill="x", padx=18, pady=16)

        current_display = self.settings.get("hotkey_display", "Ctrl + Alt + T")
        self.btn_capture = ctk.CTkButton(
            hero_inner,
            text=f"🎯 지금 화면 영역 캡처 & 번역 ({current_display})",
            font=ctk.CTkFont(family="Malgun Gothic", size=16, weight="bold"),
            height=50,
            corner_radius=12,
            fg_color=("#2563eb", "#3b82f6"),
            text_color="#ffffff",
            hover_color=("#1d4ed8", "#2563eb"),
            command=self.start_capture
        )
        self.btn_capture.pack(fill="x", pady=(0, 14))

        quick_row = ctk.CTkFrame(hero_inner, fg_color="transparent")
        quick_row.pack(fill="x")

        ctk.CTkLabel(
            quick_row,
            text="단축키:",
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            text_color=("#1e293b", "#f8fafc")
        ).pack(side="left", padx=(0, 8))

        self.hotkey_option = ctk.CTkOptionMenu(
            quick_row,
            values=list(HOTKEY_PRESETS.keys()),
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            width=145,
            height=32,
            corner_radius=8,
            fg_color=("#f1f5f9", "#334155"),
            text_color=("#0f172a", "#f8fafc"),
            button_color=("#cbd5e1", "#475569"),
            command=self.on_hotkey_changed
        )
        self.hotkey_option.set(current_display)
        self.hotkey_option.pack(side="left", padx=(0, 16))

        self.clip_switch = ctk.CTkSwitch(
            quick_row,
            text="📋 클립보드 스크린샷 자동 번역 (Win+Shift+S)",
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            text_color=("#1e293b", "#f8fafc"),
            command=self.on_clipboard_toggle,
            switch_width=40,
            switch_height=22,
            progress_color=("#2563eb", "#3b82f6")
        )
        if self.settings.get("auto_clipboard", False):
            self.clip_switch.select()
        else:
            self.clip_switch.deselect()
        self.clip_switch.pack(side="right")

        # 3. Language & OCR Settings Card
        lang_card = ctk.CTkFrame(
            inner,
            corner_radius=14,
            fg_color=("#ffffff", "#1e293b"),
            border_width=1,
            border_color=("#cbd5e1", "#334155")
        )
        lang_card.pack(fill="x", pady=(0, 16), ipady=4)

        lang_inner = ctk.CTkFrame(lang_card, fg_color="transparent")
        lang_inner.pack(fill="x", padx=18, pady=14)

        ctk.CTkLabel(
            lang_inner,
            text="🌐 언어 및 OCR 인식 설정",
            font=ctk.CTkFont(family="Malgun Gothic", size=14, weight="bold"),
            text_color=("#0f172a", "#f8fafc")
        ).pack(anchor="w", pady=(0, 10))

        # Language dropdowns row
        select_row = ctk.CTkFrame(lang_inner, fg_color="transparent")
        select_row.pack(fill="x", pady=(0, 12))

        # Source
        src_box = ctk.CTkFrame(select_row, fg_color="transparent")
        src_box.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkLabel(
            src_box,
            text="번역 원본 언어",
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            text_color=("#475569", "#94a3b8")
        ).pack(anchor="w")

        curr_src = self.settings.get("source_lang", "auto")
        src_name = next((k for k, v in SOURCE_LANGUAGES.items() if v == curr_src), "🌐 자동 감지 (Auto)")
        self.src_menu = ctk.CTkOptionMenu(
            src_box,
            values=list(SOURCE_LANGUAGES.keys()),
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            corner_radius=8,
            height=34,
            fg_color=("#f1f5f9", "#334155"),
            text_color=("#0f172a", "#f8fafc"),
            button_color=("#cbd5e1", "#475569"),
            command=self.on_language_changed
        )
        self.src_menu.set(src_name)
        self.src_menu.pack(fill="x", pady=(4, 0))

        # Arrow indicator
        ctk.CTkLabel(
            select_row,
            text="➔",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=("#2563eb", "#60a5fa")
        ).pack(side="left", padx=6, pady=(18, 0))

        # Target
        tgt_box = ctk.CTkFrame(select_row, fg_color="transparent")
        tgt_box.pack(side="left", fill="x", expand=True, padx=(8, 0))
        ctk.CTkLabel(
            tgt_box,
            text="번역 대상 언어",
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            text_color=("#475569", "#94a3b8")
        ).pack(anchor="w")

        curr_tgt = self.settings.get("target_lang", "ko")
        tgt_name = next((k for k, v in LANGUAGES.items() if v == curr_tgt), "한국어 (Korean)")
        self.tgt_menu = ctk.CTkOptionMenu(
            tgt_box,
            values=list(LANGUAGES.keys()),
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            corner_radius=8,
            height=34,
            fg_color=("#f1f5f9", "#334155"),
            text_color=("#0f172a", "#f8fafc"),
            button_color=("#cbd5e1", "#475569"),
            command=self.on_language_changed
        )
        self.tgt_menu.set(tgt_name)
        self.tgt_menu.pack(fill="x", pady=(4, 0))

        # OCR Model Selection Row
        ocr_row = ctk.CTkFrame(lang_inner, fg_color="transparent")
        ocr_row.pack(fill="x")

        ctk.CTkLabel(
            ocr_row,
            text="EasyOCR 인식 모델:",
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            text_color=("#1e293b", "#f8fafc")
        ).pack(side="left", padx=(0, 10))

        curr_ocr = self.settings.get("ocr_languages", ["ko", "en"])
        matched_preset = "한국어 + 영어 (권장)"
        for k, v in OCR_LANG_PRESETS.items():
            if set(v) == set(curr_ocr):
                matched_preset = k
                break

        self.ocr_menu = ctk.CTkOptionMenu(
            ocr_row,
            values=list(OCR_LANG_PRESETS.keys()),
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            corner_radius=8,
            height=34,
            width=210,
            fg_color=("#f1f5f9", "#334155"),
            text_color=("#0f172a", "#f8fafc"),
            button_color=("#cbd5e1", "#475569"),
            command=self.on_ocr_preset_changed
        )
        self.ocr_menu.set(matched_preset)
        self.ocr_menu.pack(side="left")

        # 4. Convenience Preferences Card (Includes In-Place Overlay Option!)
        pref_card = ctk.CTkFrame(
            inner,
            corner_radius=14,
            fg_color=("#ffffff", "#1e293b"),
            border_width=1,
            border_color=("#cbd5e1", "#334155")
        )
        pref_card.pack(fill="x", pady=(0, 16))

        pref_inner = ctk.CTkFrame(pref_card, fg_color="transparent")
        pref_inner.pack(fill="x", padx=18, pady=14)

        # In-Place Screen Overlay Switch (The feature requested by user!)
        self.overlay_mode_switch = ctk.CTkSwitch(
            pref_inner,
            text="✨ 화면 위에 바로 번역 (오버레이 모드 - 캡처 영역 바로 위에 표시)",
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            text_color=("#1d4ed8", "#60a5fa"),
            command=self.on_overlay_mode_toggle,
            switch_width=42,
            switch_height=22,
            progress_color=("#2563eb", "#3b82f6")
        )
        if self.settings.get("use_screen_overlay", True):
            self.overlay_mode_switch.select()
        else:
            self.overlay_mode_switch.deselect()
        self.overlay_mode_switch.pack(anchor="w", pady=(0, 10))

        pref_row2 = ctk.CTkFrame(pref_inner, fg_color="transparent")
        pref_row2.pack(fill="x")

        self.pin_switch = ctk.CTkSwitch(
            pref_row2,
            text="📌 번역창 항상 위에 고정",
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            text_color=("#1e293b", "#f8fafc"),
            command=self.on_always_top_toggle,
            switch_width=40,
            switch_height=22,
            progress_color=("#2563eb", "#3b82f6")
        )
        if self.settings.get("always_on_top", True):
            self.pin_switch.select()
        else:
            self.pin_switch.deselect()
        self.pin_switch.pack(side="left", padx=(0, 20))

        self.auto_copy_switch = ctk.CTkSwitch(
            pref_row2,
            text="⚡ 번역 완료 시 번역문 클립보드 자동 복사",
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            text_color=("#1e293b", "#f8fafc"),
            command=self.on_auto_copy_toggle,
            switch_width=40,
            switch_height=22,
            progress_color=("#2563eb", "#3b82f6")
        )
        if self.settings.get("copy_translation_auto", False):
            self.auto_copy_switch.select()
        else:
            self.auto_copy_switch.deselect()
        self.auto_copy_switch.pack(side="left")

        pref_row3 = ctk.CTkFrame(pref_inner, fg_color="transparent")
        pref_row3.pack(fill="x", pady=(10, 0))

        self.tray_switch = ctk.CTkSwitch(
            pref_row3,
            text="📥 닫기(✕) 시 완전 종료 대신 백그라운드(트레이)로 숨김 (상시 실행)",
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            text_color=("#1e293b", "#f8fafc"),
            command=self.on_tray_toggle,
            switch_width=40,
            switch_height=22,
            progress_color=("#2563eb", "#3b82f6")
        )
        if self.settings.get("minimize_to_tray", True):
            self.tray_switch.select()
        else:
            self.tray_switch.deselect()
        self.tray_switch.pack(side="left")

        # 5. Status Footer & Progress
        status_box = ctk.CTkFrame(inner, fg_color="transparent")
        status_box.pack(fill="x", side="bottom")

        self.progress_bar = ctk.CTkProgressBar(
            status_box,
            height=5,
            corner_radius=3,
            progress_color=("#2563eb", "#3b82f6")
        )
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", pady=(0, 10))

        status_line = ctk.CTkFrame(status_box, fg_color="transparent")
        status_line.pack(fill="x")

        self.status_lbl = ctk.CTkLabel(
            status_line,
            text="초기화 중...",
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            text_color=("#475569", "#94a3b8")
        )
        self.status_lbl.pack(side="left")

        btn_quit = ctk.CTkButton(
            status_line,
            text="완전 종료",
            font=ctk.CTkFont(family="Malgun Gothic", size=11, weight="bold"),
            width=70,
            height=32,
            corner_radius=8,
            fg_color="transparent",
            text_color="#ef4444",
            hover_color=("#fee2e2", "#450a0a"),
            command=self.quit_app
        )
        btn_quit.pack(side="right", padx=(6, 0))

        btn_hide_tray = ctk.CTkButton(
            status_line,
            text="트레이로 숨김",
            font=ctk.CTkFont(family="Malgun Gothic", size=11, weight="bold"),
            width=90,
            height=32,
            corner_radius=8,
            fg_color=("#3b82f6", "#2563eb"),
            text_color="#ffffff",
            hover_color=("#1d4ed8", "#1e40af"),
            command=self.hide_to_tray
        )
        btn_hide_tray.pack(side="right", padx=(6, 0))

        btn_min = ctk.CTkButton(
            status_line,
            text="작업표시줄 최소화",
            font=ctk.CTkFont(family="Malgun Gothic", size=11, weight="bold"),
            width=110,
            height=32,
            corner_radius=8,
            fg_color=("#e2e8f0", "#334155"),
            text_color=("#0f172a", "#f8fafc"),
            hover_color=("#cbd5e1", "#475569"),
            command=self.root.iconify
        )
        btn_min.pack(side="right")

    def _change_theme(self, mode):
        ctk.set_appearance_mode(mode)

    def on_ocr_initialized(self, success, error_msg=None):
        if success:
            self.ui_queue.put(("OCR_READY", "🟢 EasyOCR 딥러닝 엔진 준비 완료!"))
        else:
            self.ui_queue.put(("OCR_ERROR", f"🔴 EasyOCR 초기화 실패: {error_msg}"))

    def _setup_hotkey(self):
        hotkey_str = self.settings.get("hotkey", "<ctrl>+<alt>+t")
        self.hotkey_mgr.start_hotkey(hotkey_str)
        if self.settings.get("auto_clipboard", False):
            self.hotkey_mgr.start_clipboard_monitor()

    def on_hotkey_changed(self, selected_display):
        keycode = HOTKEY_PRESETS.get(selected_display, "<ctrl>+<alt>+t")
        self.settings["hotkey"] = keycode
        self.settings["hotkey_display"] = selected_display
        cfg.save_config(self.settings)
        self.hotkey_mgr.start_hotkey(keycode)
        self.btn_capture.configure(text=f"🎯 지금 화면 영역 캡처 & 번역 ({selected_display})")
        self.status_lbl.configure(text=f"✓ 단축키 변경됨: {selected_display}", text_color=("#16a34a", "#10b981"))

    def on_clipboard_toggle(self):
        enabled = bool(self.clip_switch.get())
        self.settings["auto_clipboard"] = enabled
        cfg.save_config(self.settings)
        if enabled:
            self.hotkey_mgr.start_clipboard_monitor()
            self.status_lbl.configure(text="✓ 클립보드 스크린샷 자동 번역 활성화", text_color=("#16a34a", "#10b981"))
        else:
            self.hotkey_mgr.stop_clipboard_monitor()
            self.status_lbl.configure(text="클립보드 감지 해제됨", text_color=("#64748b", "#94a3b8"))

    def on_overlay_mode_toggle(self):
        enabled = bool(self.overlay_mode_switch.get())
        self.settings["use_screen_overlay"] = enabled
        cfg.save_config(self.settings)
        mode_str = "화면 위 오버레이 모드" if enabled else "별도 결과창 모드"
        self.status_lbl.configure(text=f"✓ 번역 표시 모드: {mode_str}", text_color=("#16a34a", "#10b981"))

    def on_language_changed(self, choice=None):
        src_code = SOURCE_LANGUAGES.get(self.src_menu.get(), "auto")
        tgt_code = LANGUAGES.get(self.tgt_menu.get(), "ko")
        self.settings["source_lang"] = src_code
        self.settings["target_lang"] = tgt_code
        cfg.save_config(self.settings)
        self.translator.set_languages(target_lang=tgt_code, source_lang=src_code)
        self.status_lbl.configure(text=f"✓ 번역 언어: {src_code.upper()} ➔ {tgt_code.upper()}", text_color=("#16a34a", "#10b981"))

    def on_ocr_preset_changed(self, preset_name):
        languages = OCR_LANG_PRESETS.get(preset_name, ["ko", "en"])
        self.settings["ocr_languages"] = languages
        cfg.save_config(self.settings)
        self.progress_bar.start()
        self.status_lbl.configure(text=f"EasyOCR 모델 변경 중 ({', '.join(languages)})...", text_color=("#d97706", "#f59e0b"))
        threading.Thread(target=lambda: self.ocr_engine.change_languages(languages), daemon=True).start()

    def on_always_top_toggle(self):
        val = bool(self.pin_switch.get())
        self.settings["always_on_top"] = val
        self.result_window.always_on_top = val
        cfg.save_config(self.settings)

    def on_auto_copy_toggle(self):
        val = bool(self.auto_copy_switch.get())
        self.settings["copy_translation_auto"] = val
        cfg.save_config(self.settings)

    def on_tray_toggle(self):
        val = bool(self.tray_switch.get())
        self.settings["minimize_to_tray"] = val
        cfg.save_config(self.settings)
        msg = "✕ 클릭 시 백그라운드(트레이)로 숨김 (상시 대기)" if val else "✕ 클릭 시 프로그램 완전 종료"
        self.status_lbl.configure(text=f"✓ {msg}", text_color=("#16a34a", "#10b981"))

    def show_main_window(self):
        """Restore and focus the main window from system tray"""
        self.root.deiconify()
        self.root.state('normal')
        self.root.lift()
        self.root.focus_force()

    def hide_to_tray(self):
        """Minimize/hide main window to system tray with a notification"""
        self.root.withdraw()
        if hasattr(self, 'tray_mgr') and self.tray_mgr:
            hotkey_str = self.settings.get('hotkey_display', 'Ctrl + Alt + T')
            self.tray_mgr.notify(
                "EasyOCR 번역기 백그라운드 실행 중",
                f"단축키({hotkey_str})로 언제든 번역하거나 트레이 아이콘을 더블클릭하세요."
            )

    def quit_app(self):
        """Completely exit the application"""
        try:
            if hasattr(self, 'hotkey_mgr') and self.hotkey_mgr:
                self.hotkey_mgr.cleanup()
        except Exception:
            pass
        try:
            if hasattr(self, 'tray_mgr') and self.tray_mgr:
                self.tray_mgr.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        sys.exit(0)

    def on_hotkey_triggered(self):
        self.ui_queue.put(("TRIGGER_CAPTURE", None))

    def on_clipboard_image_detected(self, img):
        self.ui_queue.put(("PROCESS_IMAGE", (img, None)))

    def start_capture(self):
        if getattr(self, "is_capturing", False):
            print("[App] Capture already active, ignoring duplicate trigger.")
            return

        if not self.ocr_engine.is_ready():
            if self.ocr_engine._is_loading:
                self.status_lbl.configure(text="EasyOCR 모델을 아직 로딩 중입니다. 잠시만 기다려 주세요.", text_color=("#d97706", "#f59e0b"))
                return
            else:
                self.status_lbl.configure(text="EasyOCR 초기화 오류 상태입니다. 로그를 확인하세요.", text_color="#ef4444")
                return

        # Close existing screen overlay before taking a new screenshot
        if hasattr(self, 'screen_overlay') and self.screen_overlay:
            self.screen_overlay.close()

        self.is_capturing = True

        def _on_complete(img, bbox):
            self.is_capturing = False
            self.process_captured_image(img, bbox)

        def _on_cancel(err=None):
            self.is_capturing = False
            self.status_lbl.configure(
                text=err if err else "캡처가 취소되었습니다.",
                text_color=("#64748b", "#94a3b8") if not err else "#ef4444"
            )

        overlay = CaptureOverlay(
            on_capture_complete=_on_complete,
            on_cancel=_on_cancel
        )
        overlay.start_capture()

    def process_captured_image(self, img, bbox=None):
        if img is None:
            self.status_lbl.configure(text="캡처된 이미지가 비어 있습니다.", text_color="#ef4444")
            return

        self.last_captured_img = img
        self.last_bbox = bbox
        tgt = self.settings.get("target_lang", "ko")
        src = self.settings.get("source_lang", "auto")

        # Check if In-Place Screen Overlay mode is enabled
        use_overlay = self.settings.get("use_screen_overlay", True) and (bbox is not None)

        if use_overlay:
            # 1. SHOW IN-PLACE OVERLAY RIGHT ON TOP OF SCREEN WHERE USER DRAGGED!
            x, y, w, h = bbox
            self.screen_overlay.show_at(x, y, w, h, img, is_loading=True)
        else:
            # 2. Or show in floating Detail Result Window
            self.result_window.show_capture(img, target_lang=tgt, source_lang=src)

        self.progress_bar.start()
        self.status_lbl.configure(text="🔍 화면 글자 인식(EasyOCR) 및 번역 진행 중...", text_color=("#2563eb", "#3b82f6"))

        threading.Thread(target=self._worker_ocr_and_translate, args=(img, use_overlay), daemon=True).start()

    def _worker_ocr_and_translate(self, img, use_overlay):
        try:
            full_text, raw_results = self.ocr_engine.recognize_image(img)

            # Group OCR bounding boxes into structured semantic blocks (headings, paragraphs, bullets)
            blocks = group_ocr_into_blocks(raw_results, img.width)

            if not blocks and not full_text.strip():
                self.ui_queue.put(("SHOW_ERROR", ("이미지에서 텍스트를 찾지 못했습니다.", use_overlay)))
                return

            tgt = self.settings.get("target_lang", "ko")
            src = self.settings.get("source_lang", "auto")

            if blocks:
                # Batch translate blocks cleanly preserving full context
                block_texts = [b['text'] for b in blocks]
                batch_query = "\n".join(block_texts)
                trans_batch = self.translator.translate(batch_query, target_lang=tgt, source_lang=src)
                trans_lines = [l.strip() for l in trans_batch.split("\n") if l.strip()]

                if len(trans_lines) == len(blocks):
                    for i, b in enumerate(blocks):
                        b['trans_text'] = trans_lines[i]
                else:
                    for b in blocks:
                        b['trans_text'] = self.translator.translate(b['text'], target_lang=tgt, source_lang=src)

                full_orig = "\n\n".join(b['text'] for b in blocks)
                full_trans = "\n\n".join(b['trans_text'] for b in blocks)

                # Render in-place layout replacement image
                trans_img = render_in_place_translation(img, blocks)
            else:
                full_orig = full_text
                full_trans = self.translator.translate(full_text, target_lang=tgt, source_lang=src)
                trans_img = img

            if self.settings.get("copy_translation_auto", False) and full_trans:
                try:
                    import pyperclip
                    pyperclip.copy(full_trans)
                except Exception:
                    pass

            self.ui_queue.put(("SHOW_AR_RESULT", (img, trans_img, blocks, full_orig, full_trans, use_overlay)))
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[App] Processing error: {e}\n{tb}")
            self.ui_queue.put(("SHOW_ERROR", (f"처리 중 오류: {e}", use_overlay)))

    def open_detailed_result(self, orig, trans):
        """Called when user clicks '상세' on the in-place screen overlay"""
        tgt = self.settings.get("target_lang", "ko")
        src = self.settings.get("source_lang", "auto")
        if self.last_captured_img:
            self.result_window.show_capture(self.last_captured_img, target_lang=tgt, source_lang=src)
        self.result_window.update_result(orig, trans)

    def retranslate_text(self, text):
        tgt = self.settings.get("target_lang", "ko")
        src = self.settings.get("source_lang", "auto")
        return self.translator.translate(text, target_lang=tgt, source_lang=src)

    def _process_ui_queue(self):
        try:
            while not self.ui_queue.empty():
                msg_type, payload = self.ui_queue.get_nowait()
                if msg_type == "OCR_READY":
                    self.progress_bar.stop()
                    self.progress_bar.set(1.0)
                    self.status_lbl.configure(text=payload, text_color=("#16a34a", "#10b981"))
                elif msg_type == "OCR_ERROR":
                    self.progress_bar.stop()
                    self.progress_bar.set(0)
                    self.status_lbl.configure(text=payload, text_color="#ef4444")
                elif msg_type == "TRIGGER_CAPTURE":
                    if not getattr(self, "is_capturing", False):
                        self.start_capture()
                elif msg_type == "PROCESS_IMAGE":
                    img, bbox = payload
                    self.process_captured_image(img, bbox)
                elif msg_type == "SHOW_AR_RESULT":
                    self.progress_bar.stop()
                    self.progress_bar.set(1.0)
                    orig_img, trans_img, blocks, full_orig, full_trans, use_overlay = payload
                    self.status_lbl.configure(text="✓ 화면 글자 번역 완료!", text_color=("#16a34a", "#10b981"))
                    if use_overlay:
                        self.screen_overlay.update_in_place_result(orig_img, trans_img, blocks, full_orig, full_trans)
                    else:
                        self.result_window.update_result(full_orig, full_trans)
                elif msg_type == "SHOW_ERROR":
                    self.progress_bar.stop()
                    self.progress_bar.set(0)
                    err_msg, use_overlay = payload
                    self.status_lbl.configure(text=payload[0], text_color="#ef4444")
                    if use_overlay:
                        self.screen_overlay.show_error(err_msg)
                    else:
                        self.result_window.show_error(err_msg)
        except Exception as e:
            print(f"[App] UI Queue processing error: {e}")
        finally:
            self.root.after(100, self._process_ui_queue)

    def on_close(self):
        if self.settings.get("minimize_to_tray", True):
            self.hide_to_tray()
        else:
            self.quit_app()

def main():
    enable_dpi_awareness()

    # Single-instance mutex check on Windows
    mutex_name = "Local\\EasyOCR_Translator_SingleInstance_Mutex"
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
    last_error = ctypes.windll.kernel32.GetLastError()
    if last_error == 183:  # ERROR_ALREADY_EXISTS
        print("[App] Another instance is already running in background.")
        # Attempt to restore existing window if hidden/minimized
        hwnd = ctypes.windll.user32.FindWindowW(None, "EasyOCR 스크린샷 자동 번역기")
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        sys.exit(0)

    root = ctk.CTk()
    app = ModernTranslatorApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
