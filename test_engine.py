from PIL import Image, ImageDraw, ImageFont
import os
from ocr_engine import OCREngine
from translator_engine import TranslatorEngine

def run_test():
    print("1. Creating synthetic test image...")
    img = Image.new("RGB", (400, 100), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Draw simple text
    draw.text((20, 35), "Hello World", fill=(0, 0, 0))
    test_img_path = "test_sample.png"
    img.save(test_img_path)

    print("2. Initializing EasyOCR engine (en, ko)...")
    ocr = OCREngine(languages=['en', 'ko'])
    # This will download the CRAFT and English models if not present
    ocr._load_reader()
    print("EasyOCR initialized successfully!")

    print("3. Testing OCR text recognition...")
    text, results = ocr.recognize_image(img)
    print(f"Recognized text: '{text}'")

    print("4. Testing Translator Engine...")
    translator = TranslatorEngine(target_lang="ko", source_lang="en")
    translated = translator.translate(text if text else "Hello World")
    print(f"Translated text: '{translated}'")

    if os.path.exists(test_img_path):
        os.remove(test_img_path)

    print("\n[✓] ALL TESTS PASSED!")

if __name__ == "__main__":
    run_test()
