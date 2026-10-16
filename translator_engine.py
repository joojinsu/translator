import urllib.request
import urllib.parse
import json

class TranslatorEngine:
    def __init__(self, target_lang="ko", source_lang="auto"):
        self.target_lang = target_lang
        self.source_lang = source_lang

    def set_languages(self, target_lang, source_lang="auto"):
        self.target_lang = target_lang
        self.source_lang = source_lang

    def translate(self, text, target_lang=None, source_lang=None):
        text = text.strip()
        if not text:
            return ""

        tgt = target_lang or self.target_lang
        src = source_lang or self.source_lang

        # 1. Primary: Direct Google Translate gtx endpoint
        try:
            encoded_text = urllib.parse.quote(text)
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={src}&tl={tgt}&dt=t&q={encoded_text}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=6) as response:
                result = json.loads(response.read().decode("utf-8"))
                if result and isinstance(result, list) and len(result) > 0 and isinstance(result[0], list):
                    translated_pieces = [sentence[0] for sentence in result[0] if sentence and isinstance(sentence, list) and sentence[0]]
                    translated = "".join(translated_pieces).strip()
                    if translated:
                        return translated
        except Exception as e:
            print(f"[TranslatorEngine] Direct Google gtx fallback: {e}")

        # 2. Secondary: Direct Google Translate dict-chrome-ex endpoint
        try:
            encoded_text = urllib.parse.quote(text)
            url = f"https://translate.googleapis.com/translate_a/single?client=dict-chrome-ex&sl={src}&tl={tgt}&dt=t&q={encoded_text}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=6) as response:
                result = json.loads(response.read().decode("utf-8"))
                if result and isinstance(result, list) and len(result) > 0 and isinstance(result[0], list):
                    translated_pieces = [sentence[0] for sentence in result[0] if sentence and isinstance(sentence, list) and sentence[0]]
                    translated = "".join(translated_pieces).strip()
                    if translated:
                        return translated
        except Exception as e:
            print(f"[TranslatorEngine] Direct Google chrome-ex fallback: {e}")

        # 3. Tertiary: deep-translator GoogleTranslator
        try:
            from deep_translator import GoogleTranslator
            res = GoogleTranslator(source=src, target=tgt).translate(text)
            if res:
                return res.strip()
        except Exception as e:
            print(f"[TranslatorEngine] deep-translator error: {e}")

        # 4. Quaternary: MyMemory Translation API fallback
        try:
            from deep_translator import MyMemoryTranslator
            res = MyMemoryTranslator(source=src if src != "auto" else "en", target=tgt).translate(text[:450])
            if res:
                return res.strip()
        except Exception as e:
            print(f"[TranslatorEngine] MyMemory error: {e}")

        return f"[번역 오류: 서버와 통신할 수 없습니다. 잠시 후 다시 시도해 주세요.]"

    def translate_items(self, items, target_lang=None, source_lang=None):
        """
        Translates a list of (bbox, orig_text, prob) items.
        Returns a list of (bbox, orig_text, trans_text).
        Uses ultra-fast batch translation with fallback to individual items.
        """
        if not items:
            return []

        tgt = target_lang or self.target_lang
        src = source_lang or self.source_lang

        clean_items = []
        for bbox, text, prob in items:
            t = text.strip()
            if t:
                clean_items.append((bbox, t, prob))

        if not clean_items:
            return []

        orig_texts = [item[1] for item in clean_items]

        # 1. Try newline-joined batch translation
        batch_query = "\n".join(orig_texts)
        translated_batch = self.translate(batch_query, target_lang=tgt, source_lang=src)

        lines = [line.strip() for line in translated_batch.split("\n")]

        # Check if line count matches perfectly
        if len(lines) == len(orig_texts):
            result = []
            for i, (bbox, o_text, _) in enumerate(clean_items):
                result.append((bbox, o_text, lines[i]))
            return result

        # 2. If line counts mismatch, translate individually
        print(f"[TranslatorEngine] Batch mismatch ({len(lines)} vs {len(orig_texts)}), translating individually...")
        result = []
        for bbox, o_text, _ in clean_items:
            t_res = self.translate(o_text, target_lang=tgt, source_lang=src)
            result.append((bbox, o_text, t_res))
        return result
