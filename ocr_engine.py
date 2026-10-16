import os
import sys
import threading
import traceback
import numpy as np
from PIL import Image

def get_model_dir():
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    local_dir = os.path.join(base_dir, "models")
    if os.path.exists(local_dir):
        return local_dir
    return None

class OCREngine:
    def __init__(self, languages=None, gpu=False):
        if languages is None:
            languages = ['ko', 'en']
        self.languages = languages
        self.gpu = gpu
        self.reader = None
        self._is_loading = False
        self._lock = threading.Lock()
        self.on_ready_callback = None
        self.init_error = None

    def initialize_async(self, callback=None):
        if callback:
            self.on_ready_callback = callback
        t = threading.Thread(target=self._load_reader, daemon=True)
        t.start()

    def _load_reader(self):
        with self._lock:
            if self.reader is not None:
                if self.on_ready_callback:
                    self.on_ready_callback(True)
                return
            self._is_loading = True
            self.init_error = None
            try:
                import torch
                has_gpu = self.gpu and torch.cuda.is_available()
                import easyocr
                model_dir = get_model_dir()
                kwargs = {
                    "gpu": has_gpu,
                    "verbose": False,
                    "quantize": False  # Disable quantization for PyTorch 2.14+ compatibility
                }
                if model_dir:
                    kwargs["model_storage_directory"] = model_dir

                self.reader = easyocr.Reader(self.languages, **kwargs)
                self._is_loading = False
                if self.on_ready_callback:
                    self.on_ready_callback(True)
            except Exception as e:
                self._is_loading = False
                self.init_error = str(e)
                tb = traceback.format_exc()
                print(f"[OCREngine] Error initializing EasyOCR: {e}\n{tb}")
                try:
                    log_path = os.path.join(os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__), "ocr_error.log")
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(f"=== EasyOCR Init Error ===\n{tb}\n")
                except Exception:
                    pass

                if self.on_ready_callback:
                    self.on_ready_callback(False, str(e))

    def change_languages(self, languages):
        if self.languages != languages:
            self.languages = languages
            with self._lock:
                self.reader = None
            self.initialize_async()

    def is_ready(self):
        return self.reader is not None and not self._is_loading

    def recognize_image(self, image_or_path):
        """
        Takes a PIL.Image or path, returns combined string and raw results.
        """
        if self.reader is None:
            self._load_reader()

        if self.reader is None:
            err = self.init_error or "EasyOCR 엔진이 로드되지 않았습니다."
            raise RuntimeError(f"EasyOCR 초기화 오류: {err}")

        # Convert PIL Image to numpy array if needed
        if isinstance(image_or_path, Image.Image):
            img_np = np.array(image_or_path.convert('RGB'))
        elif isinstance(image_or_path, str):
            img_np = image_or_path
        elif isinstance(image_or_path, np.ndarray):
            img_np = image_or_path
        else:
            raise ValueError("지원하지 않는 이미지 형식입니다.")

        results = self.reader.readtext(img_np)
        if not results:
            return "", []

        # 1. Cluster boxes into lines based on vertical overlap
        valid_items = []
        for bbox, text, prob in results:
            clean = text.strip()
            if not clean or prob < 0.15:
                continue
            y_coords = [p[1] for p in bbox]
            x_coords = [p[0] for p in bbox]
            y_mid = (min(y_coords) + max(y_coords)) / 2.0
            h = max(y_coords) - min(y_coords)
            valid_items.append({
                'bbox': bbox,
                'text': clean,
                'prob': prob,
                'y_mid': y_mid,
                'h': max(10, h),
                'x_left': min(x_coords)
            })

        if not valid_items:
            return "", []

        # Sort primarily by vertical position
        valid_items.sort(key=lambda x: x['y_mid'])

        # Group words belonging to the same horizontal line
        raw_lines = []
        current_line = [valid_items[0]]
        for item in valid_items[1:]:
            ref_h = current_line[-1]['h']
            if abs(item['y_mid'] - current_line[-1]['y_mid']) < ref_h * 0.65:
                current_line.append(item)
            else:
                current_line.sort(key=lambda x: x['x_left'])
                raw_lines.append(" ".join(x['text'] for x in current_line))
                current_line = [item]

        if current_line:
            current_line.sort(key=lambda x: x['x_left'])
            raw_lines.append(" ".join(x['text'] for x in current_line))

        # 2. Reconstruct lines into cohesive sentences and paragraphs
        paragraphs = []
        current_para = ""
        for line in raw_lines:
            l = line.strip()
            if not l:
                if current_para:
                    paragraphs.append(current_para)
                    current_para = ""
                continue

            is_bullet = l.startswith(('•', '-', '*', '1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.'))

            if not current_para:
                current_para = l
            elif is_bullet:
                paragraphs.append(current_para)
                current_para = l
            elif len(current_para) < 35 and not current_para.endswith(('.', ':', '!', '?')):
                # Short line without ending punctuation is likely a title/heading
                paragraphs.append(current_para)
                current_para = l
            else:
                # Merge wrapped sentence lines
                if current_para.endswith('-'):
                    current_para = current_para[:-1] + l
                else:
                    current_para += ' ' + l

        if current_para:
            paragraphs.append(current_para)

        full_text = "\n\n".join(paragraphs)
        return full_text, results
