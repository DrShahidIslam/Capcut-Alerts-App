"""Simple featured image generator (PNG) with no external dependencies.

We keep this intentionally lightweight so the pipeline can always attach *some* image
(even when AI generation is unavailable).
"""

from __future__ import annotations

import re
import struct
import zlib


# 5x7 bitmap font for uppercase A-Z, digits, and a few punctuation chars.
# Each character maps to 7 strings of length 5 using '1' for a filled pixel.
FONT_5X7: dict[str, list[str]] = {
    " ": ["00000"] * 7,
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    ":": ["00000", "00100", "00100", "00000", "00100", "00100", "00000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "00100", "00100"],
    "/": ["00001", "00010", "00100", "01000", "10000", "00000", "00000"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01110"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "J": ["00111", "00010", "00010", "00010", "10010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
}

APP_TAGLINES = {
    "capcut": "TEMPLATES",
    "inshot": "SIMPLE EDITS",
    "vn": "DESIGN",
    "canva": "DESIGN",
    "kinemaster": "PRO EDITS",
    "alight motion": "MOTION",
    "premiere rush": "ADOBE",
    "filmora": "EASY FX",
}

APP_COLORS = [
    (46, 171, 255),
    (255, 170, 58),
    (108, 233, 190),
]


def render_featured_image_png(title: str, width: int = 1200, height: int = 630) -> bytes:
    """Return PNG bytes for a simple featured image with the given title."""

    safe_title = (title or "CapCut Guide").strip()
    entities = _extract_entities(safe_title)

    pixels = bytearray(width * height * 4)

    # Background gradient.
    top = (12, 32, 50)
    bottom = (6, 90, 86)
    for y in range(height):
        t = y / max(1, height - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(width):
            _set_px(pixels, width, x, y, r, g, b, 255)

    # Diagonal accent stripes.
    for y in range(height):
        for x in range(width):
            if ((x + y) % 140) < 10:
                _blend_px(pixels, width, x, y, 255, 255, 255, 18)

    if len(entities) >= 2:
        _draw_comparison_layout(pixels, width, height, entities)
    else:
        _draw_title_layout(pixels, width, height, safe_title)

    return _encode_png_rgba(width, height, bytes(pixels))


def _extract_entities(title: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", title.strip())
    normalized = re.sub(r"\bversus\b", "vs", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bvs\.\b", "vs", normalized, flags=re.IGNORECASE)
    parts = [part.strip(" -:|\t").strip() for part in re.split(r"\bvs\b", normalized, flags=re.IGNORECASE) if part.strip()]

    canon = {
        "capcut": "CapCut",
        "inshot": "InShot",
        "canva": "Canva",
        "vn": "VN",
        "kinemaster": "KineMaster",
        "alight motion": "Alight Motion",
        "premiere rush": "Premiere Rush",
        "filmora": "Filmora",
    }

    cleaned: list[str] = []
    seen = set()
    for raw in parts:
        simple = re.sub(r"\s+", " ", raw.lower()).strip()
        name = canon.get(simple) or raw.strip().title()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(name)

    if not cleaned:
        cleaned = ["CapCut"]

    if any(name.lower() == "capcut" for name in cleaned) and cleaned[0].lower() != "capcut":
        cleaned = ["CapCut"] + [name for name in cleaned if name.lower() != "capcut"]

    return cleaned


def _draw_comparison_layout(pixels: bytearray, width: int, height: int, entities: list[str]) -> None:
    margin = 60
    gap = 26
    entities = entities[:3]
    header = " VS ".join(entities)

    badge_w = 320
    badge_h = 54
    _fill_rect(pixels, width, 40, 36, badge_w, badge_h, 18, 34, 52, 210)
    _stroke_rect(pixels, width, 40, 36, badge_w, badge_h, 255, 255, 255, 70)
    _draw_text(pixels, width, height, 62, 52, "COMPARISON GUIDE", 5, (255, 255, 255, 210))

    title_text = _to_font_text(header)
    lines = _wrap_text(title_text, max_pixels=int(width * 0.84), scale=9)
    start_y = 120
    for idx, line in enumerate(lines[:2]):
        line_w = _measure_text_pixels(line, 9)
        x = max(40, (width - line_w) // 2)
        y = start_y + idx * (7 * 9 + 10)
        _draw_text(pixels, width, height, x + 3, y + 3, line, 9, (0, 0, 0, 140))
        _draw_text(pixels, width, height, x, y, line, 9, (255, 255, 255, 235))

    card_y = height - 210
    card_h = 150
    card_w = int((width - margin * 2 - gap * (len(entities) - 1)) / max(1, len(entities)))

    for idx, name in enumerate(entities):
        x = margin + idx * (card_w + gap)
        color = APP_COLORS[idx % len(APP_COLORS)]
        _fill_rect(pixels, width, x, card_y, card_w, card_h, color[0], color[1], color[2], 200)
        _stroke_rect(pixels, width, x, card_y, card_w, card_h, 255, 255, 255, 90)

        label = _to_font_text(name)
        label_scale = 8
        label_w = _measure_text_pixels(label, label_scale)
        label_x = x + max(16, (card_w - label_w) // 2)
        label_y = card_y + 28
        _draw_text(pixels, width, height, label_x + 2, label_y + 2, label, label_scale, (0, 0, 0, 120))
        _draw_text(pixels, width, height, label_x, label_y, label, label_scale, (255, 255, 255, 235))

        key = name.lower()
        tagline = APP_TAGLINES.get(key, "EDITOR")
        tagline_scale = 5
        tag_text = _to_font_text(tagline)
        tag_w = _measure_text_pixels(tag_text, tagline_scale)
        tag_x = x + max(16, (card_w - tag_w) // 2)
        tag_y = card_y + 92
        _draw_text(pixels, width, height, tag_x, tag_y, tag_text, tagline_scale, (255, 255, 255, 220))


def _draw_title_layout(pixels: bytearray, width: int, height: int, title: str) -> None:
    text = _to_font_text(title)

    max_text_width = int(width * 0.84)
    scale = 10
    lines = _wrap_text(text, max_pixels=max_text_width, scale=scale)
    block_h = len(lines) * (7 * scale + 8)
    start_y = max(40, (height - block_h) // 2)

    for idx, line in enumerate(lines):
        line_w = _measure_text_pixels(line, scale)
        x = max(40, (width - line_w) // 2)
        y = start_y + idx * (7 * scale + 8)

        # Shadow.
        _draw_text(pixels, width, height, x + 4, y + 4, line, scale, (0, 0, 0, 140))
        # Foreground.
        _draw_text(pixels, width, height, x, y, line, scale, (255, 255, 255, 235))

    _draw_text(pixels, width, height, 52, height - 70, "CAPCUT GUIDE", 5, (255, 255, 255, 190))


def _to_font_text(value: str) -> str:
    # Keep it readable with the limited bitmap font.
    upper = value.upper()
    upper = upper.replace("VS.", "VS")
    upper = upper.replace("VERSUS", "VS")
    # Remove characters we cannot render.
    cleaned = []
    for ch in upper:
        if ch in FONT_5X7:
            cleaned.append(ch)
        elif ch.isalnum():
            cleaned.append(ch)
        else:
            cleaned.append(" ")
    return "".join(cleaned)


def _wrap_text(text: str, max_pixels: int, scale: int) -> list[str]:
    words = [w for w in text.split() if w]
    if not words:
        return ["CAPCUT"]

    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = (" ".join(current + [word])).strip()
        if _measure_text_pixels(candidate, scale) <= max_pixels or not current:
            current.append(word)
            continue
        lines.append(" ".join(current))
        current = [word]

    if current:
        lines.append(" ".join(current))

    # Keep images tidy: at most 3 lines.
    if len(lines) > 3:
        joined = " ".join(lines)
        lines = [joined[:40].rstrip(), joined[40:80].rstrip(), joined[80:120].rstrip()]
        lines = [line.strip() for line in lines if line.strip()]

    return lines


def _measure_text_pixels(text: str, scale: int) -> int:
    # 5 px wide glyph + 1 px gap.
    glyph = 6 * scale
    return max(0, len(text) * glyph - scale)


def _draw_text(pixels: bytearray, width: int, height: int, x: int, y: int, text: str, scale: int, rgba: tuple[int, int, int, int]) -> None:
    r, g, b, a = rgba
    cursor = x
    for ch in text:
        glyph = FONT_5X7.get(ch) or FONT_5X7.get(" ")
        if glyph is None:
            cursor += 6 * scale
            continue
        for row in range(7):
            bits = glyph[row]
            for col in range(5):
                if bits[col] != "1":
                    continue
                px = cursor + col * scale
                py = y + row * scale
                for dy in range(scale):
                    yy = py + dy
                    if yy < 0 or yy >= height:
                        continue
                    for dx in range(scale):
                        xx = px + dx
                        if xx < 0 or xx >= width:
                            continue
                        _blend_px(pixels, width, xx, yy, r, g, b, a)
        cursor += 6 * scale


def _fill_rect(pixels: bytearray, width: int, x: int, y: int, w: int, h: int, r: int, g: int, b: int, a: int) -> None:
    for yy in range(y, y + h):
        if yy < 0:
            continue
        if yy >= 0 and yy >= (len(pixels) // (width * 4)):
            break
        for xx in range(x, x + w):
            if xx < 0 or xx >= width:
                continue
            _blend_px(pixels, width, xx, yy, r, g, b, a)


def _stroke_rect(pixels: bytearray, width: int, x: int, y: int, w: int, h: int, r: int, g: int, b: int, a: int) -> None:
    for xx in range(x, x + w):
        _blend_px(pixels, width, xx, y, r, g, b, a)
        _blend_px(pixels, width, xx, y + h - 1, r, g, b, a)
    for yy in range(y, y + h):
        _blend_px(pixels, width, x, yy, r, g, b, a)
        _blend_px(pixels, width, x + w - 1, yy, r, g, b, a)


def _set_px(pixels: bytearray, width: int, x: int, y: int, r: int, g: int, b: int, a: int) -> None:
    idx = (y * width + x) * 4
    pixels[idx: idx + 4] = bytes((r, g, b, a))


def _blend_px(pixels: bytearray, width: int, x: int, y: int, r: int, g: int, b: int, a: int) -> None:
    idx = (y * width + x) * 4
    br, bg, bb, ba = pixels[idx], pixels[idx + 1], pixels[idx + 2], pixels[idx + 3]
    alpha = a / 255.0
    inv = 1.0 - alpha
    nr = int(br * inv + r * alpha)
    ng = int(bg * inv + g * alpha)
    nb = int(bb * inv + b * alpha)
    na = max(ba, a)
    pixels[idx: idx + 4] = bytes((nr, ng, nb, na))


def _encode_png_rgba(width: int, height: int, rgba_bytes: bytes) -> bytes:
    # PNG scanlines are prefixed with a filter byte per row.
    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type 0
        start = y * stride
        raw.extend(rgba_bytes[start: start + stride])

    compressor = zlib.compressobj(level=9)
    compressed = compressor.compress(bytes(raw)) + compressor.flush()

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    chunks = [
        _png_chunk(b"IHDR", ihdr),
        _png_chunk(b"IDAT", compressed),
        _png_chunk(b"IEND", b""),
    ]
    return b"\x89PNG\r\n\x1a\n" + b"".join(chunks)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    length = struct.pack(">I", len(data))
    crc = zlib.crc32(tag)
    crc = zlib.crc32(data, crc)
    crc_bytes = struct.pack(">I", crc & 0xFFFFFFFF)
    return length + tag + data + crc_bytes
