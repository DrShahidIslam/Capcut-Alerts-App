"""Simple featured image generator (PNG) with no external dependencies.

We keep this intentionally lightweight so the pipeline can always attach *some* image
(even when AI generation is unavailable).
"""

from __future__ import annotations

import struct
import zlib


# 5x7 bitmap font for uppercase A-Z, digits, and a few punctuation chars.
# Each character maps to 7 strings of length 5 using '1' for a filled pixel.
FONT_5X7: dict[str, list[str]] = {
    " ": ["00000"] * 7,
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    ":": ["00000", "00100", "00100", "00000", "00100", "00100", "00000"],
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


def render_featured_image_png(title: str, width: int = 1200, height: int = 630) -> bytes:
    """Return PNG bytes for a simple featured image with the given title."""

    safe_title = (title or "CapCut Guide").strip()
    text = _to_font_text(safe_title)

    pixels = bytearray(width * height * 4)

    # Background gradient.
    top = (14, 32, 52)
    bottom = (10, 72, 80)
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
            if ((x + y) % 120) < 10:
                _blend_px(pixels, width, x, y, 255, 255, 255, 24)

    # Title block.
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

    return _encode_png_rgba(width, height, bytes(pixels))


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
