"""Template-based image composition with Pillow.

A template is JSON data (stored in the `templates` table), so designs can be
changed or added from the dashboard without touching backend code:

{
  "background": {"type": "gradient", "from": "{primary}", "to": "#0f172a"},
  "elements": [
    {"type": "image", "slot": "image", "box": [0, 0, 1080, 800], "fit": "cover", "radius": 0},
    {"type": "rect", "box": [0, 760, 1080, 590], "color": "#000000", "opacity": 0.35},
    {"type": "text", "slot": "headline", "box": [60, 820, 960, 260], "font_size": 84,
     "min_font_size": 40, "color": "#ffffff", "bold": true, "align": "left", "max_lines": 3},
    {"type": "logo", "box": [60, 40, 160, 160]}
  ]
}

Slots: image, headline, subtitle, cta, footer, category, company. Color tokens:
{primary} and {secondary} come from the brand profile.

The output always satisfies Instagram's image rules (JPEG, <= 8 MB,
aspect ratio between 4:5 and 1.91:1).
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

from app.core.errors import ValidationFailed

logger = logging.getLogger(__name__)

IG_MIN_RATIO = 4 / 5  # portrait limit (width / height)
IG_MAX_RATIO = 1.91  # landscape limit
IG_MAX_BYTES = 8 * 1024 * 1024
IG_MAX_WIDTH = 1440
UPLOAD_MAX_BYTES = 20 * 1024 * 1024

_FONT_CANDIDATES = {
    False: [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ],
    True: [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ],
}


@lru_cache(maxsize=64)
def _font(size: int, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES[bold]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _color(value: str | None, tokens: dict[str, str], default: str = "#000000") -> str:
    value = value or default
    for k, v in tokens.items():
        value = value.replace("{" + k + "}", v)
    return value


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    try:
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (0, 0, 0)


@dataclass
class RenderContent:
    headline: str = ""
    subtitle: str = ""
    cta: str = ""
    footer: str = ""
    category: str = ""
    company: str = ""
    image: bytes | None = None
    logo: bytes | None = None
    tokens: dict[str, str] = field(default_factory=dict)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if draw.textlength(trial, font=font) <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _fit_text(draw, text, box, size, min_size, bold, max_lines, line_spacing):
    _, _, w, h = box
    for s in range(size, min_size - 1, -2):
        font = _font(s, bold)
        lines = _wrap(draw, text, font, w)
        line_h = int(s * line_spacing)
        if len(lines) <= max_lines and line_h * len(lines) <= h:
            return font, lines, line_h
    font = _font(min_size, bold)
    lines = _wrap(draw, text, font, w)[:max_lines]
    if lines:
        lines[-1] = lines[-1].rstrip(".") + "…"
    return font, lines, int(min_size * line_spacing)


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size[0], size[1]], radius=radius, fill=255)
    return mask


def _paste_image(canvas: Image.Image, data: bytes, box, fit: str, radius: int, opacity: float) -> None:
    x, y, w, h = box
    try:
        src = Image.open(io.BytesIO(data))
        src = ImageOps.exif_transpose(src).convert("RGBA")
    except (UnidentifiedImageError, OSError):
        logger.warning("Skipping unreadable image in template")
        return
    if fit == "contain":
        src.thumbnail((w, h))
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        layer.paste(src, ((w - src.width) // 2, (h - src.height) // 2), src)
        src = layer
    else:
        src = ImageOps.fit(src, (w, h), method=Image.Resampling.LANCZOS)
    if opacity < 1:
        alpha = src.getchannel("A").point(lambda a: int(a * opacity))
        src.putalpha(alpha)
    mask = src.getchannel("A")
    if radius:
        rounded = _rounded_mask((w, h), radius)
        mask = Image.composite(mask, Image.new("L", (w, h), 0), rounded)
    canvas.paste(src, (x, y), mask)


def render_template(layout: dict[str, Any], content: RenderContent, width: int = 1080, height: int = 1350) -> bytes:
    """Compose the final post image and return Instagram-ready JPEG bytes."""
    tokens = {"primary": "#1e3a8a", "secondary": "#f59e0b", **content.tokens}
    bg = layout.get("background", {"type": "color", "color": "{primary}"})
    canvas = Image.new("RGBA", (width, height), _hex_to_rgb(_color(bg.get("color"), tokens, "#1e3a8a")) + (255,))
    if bg.get("type") == "gradient":
        c1 = _hex_to_rgb(_color(bg.get("from"), tokens, "#1e3a8a"))
        c2 = _hex_to_rgb(_color(bg.get("to"), tokens, "#0f172a"))
        draw = ImageDraw.Draw(canvas)
        for yy in range(height):
            t = yy / max(height - 1, 1)
            draw.line([(0, yy), (width, yy)], fill=tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3)) + (255,))

    slots = {
        "headline": content.headline,
        "subtitle": content.subtitle,
        "cta": content.cta,
        "footer": content.footer,
        "category": content.category,
        "company": content.company,
    }
    for el in layout.get("elements", []):
        kind = el.get("type")
        box = [int(v) for v in el.get("box", [0, 0, width, height])]
        if kind == "image":
            if content.image:
                _paste_image(canvas, content.image, box, el.get("fit", "cover"), int(el.get("radius", 0)), float(el.get("opacity", 1)))
            elif el.get("placeholder_color"):
                overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
                ImageDraw.Draw(overlay).rectangle([box[0], box[1], box[0] + box[2], box[1] + box[3]], fill=_hex_to_rgb(_color(el["placeholder_color"], tokens)) + (255,))
                canvas = Image.alpha_composite(canvas, overlay)
        elif kind == "logo":
            if content.logo:
                _paste_image(canvas, content.logo, box, "contain", 0, 1.0)
        elif kind == "rect":
            overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            fill = _hex_to_rgb(_color(el.get("color"), tokens)) + (int(255 * float(el.get("opacity", 1))),)
            ImageDraw.Draw(overlay).rounded_rectangle([box[0], box[1], box[0] + box[2], box[1] + box[3]], radius=int(el.get("radius", 0)), fill=fill)
            canvas = Image.alpha_composite(canvas, overlay)
        elif kind == "text":
            text = el.get("text") or slots.get(el.get("slot", ""), "")
            for k, v in slots.items():
                text = text.replace("{" + k + "}", v or "")
            text = text.strip()
            if el.get("uppercase"):
                text = text.upper()
            if not text:
                continue
            draw = ImageDraw.Draw(canvas)
            pad = int(el.get("padding", 0))
            inner = [box[0] + pad, box[1] + pad, box[2] - 2 * pad, box[3] - 2 * pad]
            font, lines, line_h = _fit_text(
                draw,
                text,
                inner,
                int(el.get("font_size", 48)),
                int(el.get("min_font_size", 24)),
                bool(el.get("bold", False)),
                int(el.get("max_lines", 4)),
                float(el.get("line_spacing", 1.2)),
            )
            block_h = line_h * len(lines)
            valign = el.get("valign", "top")
            y0 = inner[1] + (inner[3] - block_h) // 2 if valign == "middle" else (inner[1] + inner[3] - block_h if valign == "bottom" else inner[1])
            if el.get("background"):
                widest = max((draw.textlength(line, font=font) for line in lines), default=0)
                align = el.get("align", "left")
                bx0 = inner[0] if align == "left" else (inner[0] + (inner[2] - widest) / 2 if align == "center" else inner[0] + inner[2] - widest)
                overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
                ImageDraw.Draw(overlay).rounded_rectangle(
                    [bx0 - pad, y0 - pad, bx0 + widest + pad, y0 + block_h + pad],
                    radius=int(el.get("radius", 16)),
                    fill=_hex_to_rgb(_color(el["background"], tokens)) + (255,),
                )
                canvas = Image.alpha_composite(canvas, overlay)
                draw = ImageDraw.Draw(canvas)
            color = _hex_to_rgb(_color(el.get("color"), tokens, "#ffffff"))
            for i, line in enumerate(lines):
                lw = draw.textlength(line, font=font)
                align = el.get("align", "left")
                x = inner[0] if align == "left" else (inner[0] + (inner[2] - lw) / 2 if align == "center" else inner[0] + inner[2] - lw)
                draw.text((x, y0 + i * line_h), line, font=font, fill=color)
    return to_instagram_jpeg(canvas)


def to_instagram_jpeg(img: Image.Image) -> bytes:
    """Convert to RGB JPEG within Instagram's aspect-ratio and file-size limits."""
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode in ("RGBA", "LA"):
            background.paste(img, mask=img.getchannel("A"))
        else:
            background.paste(img.convert("RGB"))
        img = background
    ratio = img.width / img.height
    if ratio < IG_MIN_RATIO:  # too tall -> crop height to 4:5
        new_h = int(img.width / IG_MIN_RATIO)
        top = (img.height - new_h) // 2
        img = img.crop((0, top, img.width, top + new_h))
    elif ratio > IG_MAX_RATIO:  # too wide -> crop width to 1.91:1
        new_w = int(img.height * IG_MAX_RATIO)
        left = (img.width - new_w) // 2
        img = img.crop((left, 0, left + new_w, img.height))
    if img.width > IG_MAX_WIDTH:
        img = img.resize((IG_MAX_WIDTH, int(img.height * IG_MAX_WIDTH / img.width)), Image.Resampling.LANCZOS)
    for quality in (92, 85, 75, 65, 55):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
        if buf.tell() <= IG_MAX_BYTES:
            return buf.getvalue()
    raise ValidationFailed("Could not compress image below Instagram's 8 MB limit.")


def load_uploaded_image(data: bytes) -> Image.Image:
    """Validate an uploaded file is a real image of reasonable size."""
    if len(data) > UPLOAD_MAX_BYTES:
        raise ValidationFailed("Image is larger than 20 MB.")
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationFailed("The uploaded file is not a valid image (use JPEG, PNG or WebP).") from exc
    if img.format not in {"JPEG", "PNG", "WEBP", "MPO"}:
        raise ValidationFailed(f"Unsupported image format {img.format}. Use JPEG, PNG or WebP.")
    if img.width < 320 or img.height < 320:
        raise ValidationFailed("Image is too small (minimum 320x320 pixels).")
    return img


def check_instagram_image(data: bytes) -> list[str]:
    """Return problems that would make Instagram reject this image (empty = OK)."""
    problems: list[str] = []
    if len(data) > IG_MAX_BYTES:
        problems.append("Image is larger than 8 MB.")
    try:
        img = Image.open(io.BytesIO(data))
    except (UnidentifiedImageError, OSError):
        return ["File is not a readable image."]
    if img.format != "JPEG":
        problems.append(f"Instagram only accepts JPEG images (got {img.format}).")
    ratio = img.width / img.height
    if ratio < IG_MIN_RATIO - 0.01 or ratio > IG_MAX_RATIO + 0.01:
        problems.append(f"Aspect ratio {ratio:.2f} is outside Instagram's 4:5 to 1.91:1 range.")
    return problems
