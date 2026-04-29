from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

_CANVAS_SIZE = (1080, 1080)
_GRADIENT_HEIGHT_RATIO = 0.45  # bottom 45% covered by dark gradient
_FONT_PATH: Path | None = None  # None = use PIL default; set to .ttf for custom font


@dataclass
class Overlay:
    """A text or badge element to composite onto the image."""
    text: str
    position: tuple[int, int]  # (x, y) — top-left anchor
    font_size: int = 64
    color: tuple[int, int, int, int] = (255, 255, 255, 255)
    max_width: int = 900  # wrap at this pixel width


def composite(
    background: Image.Image,
    content_zone: Image.Image | None,
    overlays: list[Overlay],
    output_path: Path,
) -> Path:
    """Composite background + optional content panel + text overlays → save PNG.

    Args:
        background: Full-bleed 1080×1080 base image.
        content_zone: Optional image (chart figure, scoreline graphic) placed in the
                      upper 55% of the canvas. If None, background fills the whole canvas.
        overlays: Text/badge elements drawn over the gradient zone.
        output_path: Where to write the final PNG.

    Returns:
        output_path (for chaining).
    """
    canvas = background.convert("RGBA").resize(_CANVAS_SIZE, Image.LANCZOS)

    if content_zone is not None:
        panel_h = int(_CANVAS_SIZE[1] * (1 - _GRADIENT_HEIGHT_RATIO))
        panel = content_zone.convert("RGBA").resize(
            (_CANVAS_SIZE[0], panel_h), Image.LANCZOS
        )
        canvas.paste(panel, (0, 0))

    canvas = _apply_gradient_overlay(canvas)

    draw = ImageDraw.Draw(canvas)
    for overlay in overlays:
        _draw_text(draw, overlay)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, format="PNG", optimize=True)
    return output_path


def _apply_gradient_overlay(img: Image.Image) -> Image.Image:
    """Draw a dark gradient over the bottom portion of the image for text legibility."""
    w, h = img.size
    gradient_start_y = int(h * (1 - _GRADIENT_HEIGHT_RATIO))
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(gradient_start_y, h):
        alpha = int(200 * (y - gradient_start_y) / (h - gradient_start_y))
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
    return Image.alpha_composite(img, overlay)


def _draw_text(draw: ImageDraw.ImageDraw, overlay: Overlay) -> None:
    font = _load_font(overlay.font_size)
    x, y = overlay.position
    lines = _wrap_text(draw, overlay.text, font, overlay.max_width)
    line_spacing = int(overlay.font_size * 1.25)
    for line in lines:
        draw.text((x, y), line, font=font, fill=overlay.color)
        y += line_spacing


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines, current = [], []
    for word in words:
        test = " ".join(current + [word])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] > max_width and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if _FONT_PATH and _FONT_PATH.exists():
        return ImageFont.truetype(str(_FONT_PATH), size)
    try:
        # Try common system fonts
        for name in ("arial.ttf", "Arial.ttf", "DejaVuSans-Bold.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
    except Exception:
        pass
    return ImageFont.load_default()
