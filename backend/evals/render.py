"""Render a label case's text lines to synthetic PNG artwork.

The artwork is intentionally plain (black text on white) — it tests whether the
model correctly *separates and extracts* fields, not typography. Long lines are
word-wrapped to the image width so nothing is clipped.
"""

import io

from PIL import Image, ImageDraw, ImageFont

_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Helvetica.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
)


def _load_font(size):
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap(draw, font, text, max_width):
    words = text.split()
    if not words:
        return [""]
    lines = []
    current = words[0]
    for word in words[1:]:
        trial = current + " " + word
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def render_label(
    artwork_lines,
    width=900,
    font_size=30,
    padding=44,
    line_spacing=16,
    background="white",
    color="black",
):
    font = _load_font(font_size)
    try:
        ascent, descent = font.getmetrics()
    except AttributeError:
        ascent, descent = font_size, 0
    line_height = ascent + descent + line_spacing

    # Measure with a scratch image so wrapping uses real glyph widths.
    scratch = ImageDraw.Draw(Image.new("RGB", (width, 10)))
    max_text_width = width - padding * 2
    wrapped = []
    for line in artwork_lines or [""]:
        wrapped.extend(_wrap(scratch, font, line, max_text_width))

    height = padding * 2 + line_height * max(1, len(wrapped))
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)

    y = padding
    for line in wrapped:
        draw.text((padding, y), line, fill=color, font=font)
        y += line_height

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
