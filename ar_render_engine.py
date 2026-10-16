import os
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def get_korean_font(size=12, bold=False):
    candidates = [
        "C:\\Windows\\Fonts\\malgunbd.ttf" if bold else "C:\\Windows\\Fonts\\malgun.ttf",
        "C:\\Windows\\Fonts\\malgun.ttf",
        "C:\\Windows\\Fonts\\NanumGothicBold.ttf" if bold else "C:\\Windows\\Fonts\\NanumGothic.ttf"
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

def sample_bg_and_text_color(img, min_x, min_y, max_x, max_y):
    w, h = img.size
    min_x = max(0, min_x)
    max_x = min(w - 1, max_x)
    min_y = max(0, min_y)
    max_y = min(h - 1, max_y)

    if min_x >= max_x or min_y >= max_y:
        return (255, 255, 255), (15, 23, 42)

    pixels = []
    # Sample outer border rows
    for dy in [-2, -1, 0, max_y - min_y, max_y - min_y + 1, max_y - min_y + 2]:
        cy = min_y + dy
        if 0 <= cy < h:
            step = max(1, (max_x - min_x) // 12)
            for cx in range(min_x, max_x + 1, step):
                pixels.append(img.getpixel((cx, cy))[:3])

    # Sample outer border columns
    for dx in [-2, -1, 0, max_x - min_x, max_x - min_x + 1, max_x - min_x + 2]:
        cx = min_x + dx
        if 0 <= cx < w:
            step = max(1, (max_y - min_y) // 12)
            for cy in range(min_y, max_y + 1, step):
                pixels.append(img.getpixel((cx, cy))[:3])

    if not pixels:
        return (255, 255, 255), (15, 23, 42)

    r_med = int(np.median([p[0] for p in pixels]))
    g_med = int(np.median([p[1] for p in pixels]))
    b_med = int(np.median([p[2] for p in pixels]))
    bg_color = (r_med, g_med, b_med)

    lum = 0.299 * r_med + 0.587 * g_med + 0.114 * b_med
    text_color = (15, 23, 42) if lum > 130 else (248, 250, 252)

    return bg_color, text_color

def wrap_text_by_pixels(text, font, max_width, draw):
    words = text.split(' ')
    lines = []
    curr = ""
    for w in words:
        test = curr + (" " if curr else "") + w
        b = draw.textbbox((0, 0), test, font=font)
        if (b[2] - b[0]) <= max_width or not curr:
            curr = test
        else:
            lines.append(curr)
            curr = w
    if curr:
        lines.append(curr)
    return lines

def group_ocr_into_blocks(ocr_results, img_width=1000):
    """
    Groups raw EasyOCR boxes into semantic items (headings, paragraphs, individual bullets).
    Ensures each bullet point and each heading stays at its own distinct location.
    """
    if not ocr_results:
        return []

    raw_items = []
    for item in ocr_results:
        bbox, text, prob = item[0], item[1], item[2]
        clean = text.strip()
        if not clean or prob < 0.15:
            continue
        xs = [int(p[0]) for p in bbox]
        ys = [int(p[1]) for p in bbox]
        raw_items.append({
            'text': clean,
            'x1': min(xs),
            'y1': min(ys),
            'x2': max(xs),
            'y2': max(ys),
            'y_mid': (min(ys) + max(ys)) / 2.0,
            'h': max(10, max(ys) - min(ys))
        })

    if not raw_items:
        return []

    # Sort primarily by vertical position
    raw_items.sort(key=lambda x: x['y_mid'])

    # 1. Group into visual lines (horizontal rows)
    lines = []
    curr_line = [raw_items[0]]
    for item in raw_items[1:]:
        ref_h = curr_line[-1]['h']
        if abs(item['y_mid'] - curr_line[-1]['y_mid']) < ref_h * 0.6:
            curr_line.append(item)
        else:
            curr_line.sort(key=lambda x: x['x1'])
            merged_text = " ".join(x['text'] for x in curr_line)
            lines.append({
                'text': merged_text,
                'x1': min(x['x1'] for x in curr_line),
                'y1': min(x['y1'] for x in curr_line),
                'x2': max(x['x2'] for x in curr_line),
                'y2': max(x['y2'] for x in curr_line),
                'h': max(x['y2'] for x in curr_line) - min(x['y1'] for x in curr_line)
            })
            curr_line = [item]

    if curr_line:
        curr_line.sort(key=lambda x: x['x1'])
        merged_text = " ".join(x['text'] for x in curr_line)
        lines.append({
            'text': merged_text,
            'x1': min(x['x1'] for x in curr_line),
            'y1': min(x['y1'] for x in curr_line),
            'x2': max(x['x2'] for x in curr_line),
            'y2': max(x['y2'] for x in curr_line),
            'h': max(x['y2'] for x in curr_line) - min(x['y1'] for x in curr_line)
        })

    # 2. Split lines into distinct items (Headings, Paragraphs, Individual Bullets)
    items = []
    curr = None
    for line in lines:
        t = line['text'].strip()
        x1, y1, x2, y2 = line['x1'], line['y1'], line['x2'], line['y2']
        h = line['h']

        if curr is None:
            is_heading = len(t) < 35 and not t.endswith(('.', ':', '!', '?'))
            curr = {
                'text': t,
                'box': [x1, y1, x2, y2],
                'h': h,
                'is_heading': is_heading,
                'line_count': 1
            }
            continue

        gap = y1 - curr['box'][3]
        prev_text = curr['text'].strip()

        # Check if line starts a new item:
        is_new = False
        # A. Vertical gap of 7px or more indicates a separate section/bullet
        if gap >= 7:
            is_new = True
        # B. Left margin shifts to the left (new bullet un-indented)
        elif x1 < curr['box'][0] - 6:
            is_new = True
        # C. Previous item was a short title/heading
        elif curr['is_heading']:
            is_new = True
        # D. Previous line ended with period/colon and gap >= 3px
        elif prev_text.endswith(('.', ':', '!', '?')) and gap >= 3:
            is_new = True
        # E. Explicit bullet symbols
        elif t.startswith(('•', '-', '*', '1.', '2.', '3.', '4.', '5.')):
            is_new = True

        if is_new:
            items.append(curr)
            is_heading = len(t) < 35 and not t.endswith(('.', ':', '!', '?'))
            curr = {
                'text': t,
                'box': [x1, y1, x2, y2],
                'h': h,
                'is_heading': is_heading,
                'line_count': 1
            }
        else:
            # Continuation line of same bullet or paragraph
            if curr['text'].endswith('-'):
                curr['text'] = curr['text'][:-1] + t
            else:
                curr['text'] += " " + t
            curr['box'][0] = min(curr['box'][0], x1)
            curr['box'][1] = min(curr['box'][1], y1)
            curr['box'][2] = max(curr['box'][2], x2)
            curr['box'][3] = max(curr['box'][3], y2)
            curr['line_count'] += 1

    if curr:
        items.append(curr)

    return items

def render_in_place_translation(orig_img, translated_blocks):
    """
    Renders translated text directly onto the image at the exact visual positions
    of each title, bullet point, and paragraph with proper word wrapping.
    """
    out_img = orig_img.convert("RGB").copy()
    draw = ImageDraw.Draw(out_img)
    w, h = orig_img.size

    for blk in translated_blocks:
        trans_text = blk.get('trans_text', '').strip()
        if not trans_text:
            continue

        raw_x1, raw_y1, raw_x2, raw_y2 = blk['box']
        box_w = max(raw_x2 - raw_x1, 70)
        box_h = max(raw_y2 - raw_y1, 14)
        line_cnt = max(1, blk.get('line_count', 1))

        bg_color, text_color = sample_bg_and_text_color(orig_img, raw_x1, raw_y1, raw_x2, raw_y2)

        is_heading = blk.get('is_heading', False)

        if is_heading:
            f_size = max(13, min(22, int(box_h * 0.78)))
            font = get_korean_font(size=f_size, bold=True)
            wrapped_lines = wrap_text_by_pixels(trans_text, font, min(w - raw_x1 - 10, int(box_w * 1.3)), draw)
        else:
            avg_line_h = box_h / line_cnt
            f_size = max(11, min(15, int(avg_line_h * 0.75)))
            font = get_korean_font(size=f_size, bold=False)
            wrapped_lines = wrap_text_by_pixels(trans_text, font, min(w - raw_x1 - 10, int(box_w * 1.15)), draw)

        # Measure dimensions
        line_spacing = 3
        total_text_h = 0
        max_line_w = 0
        line_heights = []
        for line in wrapped_lines:
            t_box = draw.textbbox((0, 0), line, font=font)
            lw = t_box[2] - t_box[0]
            lh = t_box[3] - t_box[1]
            max_line_w = max(max_line_w, lw)
            line_heights.append(lh)
            total_text_h += lh + line_spacing

        # Clear background with padding
        pad_x = 3
        pad_y = 2
        mask_x1 = max(0, raw_x1 - pad_x)
        mask_x2 = min(w, max(raw_x2 + pad_x, raw_x1 + max_line_w + pad_x * 2))
        mask_y1 = max(0, raw_y1 - pad_y)
        mask_y2 = min(h, max(raw_y2 + pad_y, raw_y1 + total_text_h + pad_y * 2))

        draw.rectangle([mask_x1, mask_y1, mask_x2, mask_y2], fill=bg_color)

        # Render lines cleanly
        curr_y = raw_y1
        for i, line in enumerate(wrapped_lines):
            draw.text((raw_x1, curr_y), line, fill=text_color, font=font)
            curr_y += line_heights[i] + line_spacing

    return out_img
