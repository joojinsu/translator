import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "hotkey": "<ctrl>+<alt>+t",
    "hotkey_display": "Ctrl + Alt + T",
    "ocr_languages": ["ko", "en"],
    "source_lang": "auto",
    "target_lang": "ko",
    "auto_clipboard": False,
    "always_on_top": True,
    "use_screen_overlay": True,
    "copy_translation_auto": False,
    "minimize_to_tray": True,
    "start_minimized": False
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                config = DEFAULT_CONFIG.copy()
                config.update(data)
                return config
        except Exception:
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()

def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving config: {e}")
