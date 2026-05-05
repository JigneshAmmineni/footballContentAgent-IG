"""Composites an OverlaySpec onto a background image using PIL.
Each layout is a pure function: (ImageDraw, box, spec) -> None.
The background image is assumed to be 1080x1350 (Instagram 4:5 portrait).
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from app.models.overlay_spec import OverlaySpec

# Instagram portrait dimensions
W, H = 1080, 1350
# Overlay panel covers bottom 35% of image
PANEL_TOP_RATIO = 0.65
PANEL_ALPHA = 210  # 0-255

# Colours
WHITE = (255, 255, 255)
LIGHT_GREY = (200, 200, 200)
DIM_GREY = (160, 160, 160)
ACCENT = (255, 215, 0)  # gold accent for scores/headers


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "arialbd.ttf" if bold else "arial.ttf",
        "Arial Bold.ttf" if bold else "Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def composite(background: Image.Image, spec: OverlaySpec, out_path: Path) -> None:
    """Draw spec onto background (in-place) and save to out_path."""
    img = background.convert("RGBA").resize((W, H))
    panel_top = int(H * PANEL_TOP_RATIO)
    panel_h = H - panel_top

    # Dark gradient panel
    panel = Image.new("RGBA", (W, panel_h), (0, 0, 0, 0))
    draw_panel = ImageDraw.Draw(panel)
    for y in range(panel_h):
        alpha = int(PANEL_ALPHA * (y / panel_h) ** 0.4)
        draw_panel.rectangle([(0, y), (W, y + 1)], fill=(0, 0, 0, alpha))

    img.paste(panel, (0, panel_top), panel)
    draw = ImageDraw.Draw(img)

    box = (0, panel_top, W, H)
    if spec.layout == "score_card":
        _render_score_card(draw, box, spec)
    elif spec.layout == "player_card":
        _render_player_card(draw, box, spec)
    elif spec.layout == "table_card":
        _render_table_card(draw, box, spec)
    elif spec.layout == "quote_card":
        _render_quote_card(draw, box, spec)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, "PNG")


def _cx(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, draw: ImageDraw.ImageDraw) -> int:
    """Return x so that text is horizontally centered on W."""
    bbox = draw.textbbox((0, 0), text, font=font)
    return (W - (bbox[2] - bbox[0])) // 2


def _render_score_card(draw: ImageDraw.ImageDraw, box: tuple, spec: OverlaySpec) -> None:
    x0, y0, x1, y1 = box
    pad = 20
    y = y0 + pad

    # Header
    hfont = _load_font(28)
    draw.text((_cx(spec.header, hfont, draw), y), spec.header, font=hfont, fill=DIM_GREY)
    y += 38

    # Teams + score row
    tfont = _load_font(52, bold=True)
    sfont = _load_font(68, bold=True)
    left_x = x0 + 60
    right_x = x1 - 60
    mid_x = W // 2

    # Left team
    draw.text((left_x, y), spec.left_label, font=tfont, fill=WHITE)
    # Score
    score_w = draw.textbbox((0, 0), spec.center_text, font=sfont)[2]
    draw.text((mid_x - score_w // 2, y - 8), spec.center_text, font=sfont, fill=ACCENT)
    # Right team
    right_bbox = draw.textbbox((0, 0), spec.right_label, font=tfont)
    draw.text((right_x - right_bbox[2], y), spec.right_label, font=tfont, fill=WHITE)
    y += 80

    # Scorer rows — left side vs right side
    rfont = _load_font(26)
    left_rows = [r for r in spec.rows if r.side == "left"]
    right_rows = [r for r in spec.rows if r.side == "right"]
    center_rows = [r for r in spec.rows if r.side == "center"]
    max_rows = max(len(left_rows), len(right_rows), len(center_rows), 1)
    for i in range(max_rows):
        if i < len(left_rows):
            draw.text((left_x, y), left_rows[i].label, font=rfont, fill=LIGHT_GREY)
        if i < len(right_rows):
            rb = draw.textbbox((0, 0), right_rows[i].label, font=rfont)
            draw.text((right_x - rb[2], y), right_rows[i].label, font=rfont, fill=LIGHT_GREY)
        if i < len(center_rows):
            draw.text((_cx(center_rows[i].label, rfont, draw), y), center_rows[i].label, font=rfont, fill=LIGHT_GREY)
        y += 32

    # Footer
    if spec.footer:
        ffont = _load_font(22)
        draw.text((_cx(spec.footer, ffont, draw), y1 - 38), spec.footer, font=ffont, fill=DIM_GREY)


def _render_player_card(draw: ImageDraw.ImageDraw, box: tuple, spec: OverlaySpec) -> None:
    x0, y0, x1, y1 = box
    pad = 20
    y = y0 + pad

    hfont = _load_font(28)
    draw.text((_cx(spec.header, hfont, draw), y), spec.header, font=hfont, fill=DIM_GREY)
    y += 38

    pfont = _load_font(54, bold=True)
    draw.text((_cx(spec.left_label, pfont, draw), y), spec.left_label, font=pfont, fill=WHITE)
    y += 68

    rfont = _load_font(30)
    vfont = _load_font(30, bold=True)
    col_split = W // 2
    for row in spec.rows:
        draw.text((x0 + 60, y), row.label, font=rfont, fill=LIGHT_GREY)
        if row.value:
            draw.text((col_split + 20, y), row.value, font=vfont, fill=ACCENT)
        y += 38

    if spec.footer:
        ffont = _load_font(22)
        draw.text((_cx(spec.footer, ffont, draw), y1 - 38), spec.footer, font=ffont, fill=DIM_GREY)


def _render_table_card(draw: ImageDraw.ImageDraw, box: tuple, spec: OverlaySpec) -> None:
    x0, y0, x1, y1 = box
    pad = 20
    y = y0 + pad

    hfont = _load_font(28)
    draw.text((_cx(spec.header, hfont, draw), y), spec.header, font=hfont, fill=DIM_GREY)
    y += 38

    rfont = _load_font(30)
    vfont = _load_font(30, bold=True)
    for i, row in enumerate(spec.rows):
        pos = str(i + 1) + "."
        draw.text((x0 + 40, y), pos, font=rfont, fill=DIM_GREY)
        draw.text((x0 + 80, y), row.label, font=rfont, fill=WHITE)
        if row.value:
            vb = draw.textbbox((0, 0), row.value, font=vfont)
            draw.text((x1 - 60 - vb[2], y), row.value, font=vfont, fill=ACCENT)
        y += 38

    if spec.footer:
        ffont = _load_font(22)
        draw.text((_cx(spec.footer, ffont, draw), y1 - 38), spec.footer, font=ffont, fill=DIM_GREY)


def _render_quote_card(draw: ImageDraw.ImageDraw, box: tuple, spec: OverlaySpec) -> None:
    x0, y0, x1, y1 = box
    pad = 30
    y = y0 + pad

    hfont = _load_font(28)
    draw.text((_cx(spec.header, hfont, draw), y), spec.header, font=hfont, fill=DIM_GREY)
    y += 44

    # Word-wrap the quote
    qfont = _load_font(36, bold=True)
    max_w = W - 120
    words = spec.center_text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        if draw.textbbox((0, 0), test, font=qfont)[2] <= max_w:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    draw.text((x0 + 40, y), "“", font=_load_font(60, bold=True), fill=ACCENT)
    y += 30
    for line in lines:
        draw.text((x0 + 60, y), line, font=qfont, fill=WHITE)
        y += 44

    # Attribution
    if spec.left_label:
        afont = _load_font(26)
        draw.text((x0 + 60, y + 8), f"— {spec.left_label}", font=afont, fill=DIM_GREY)

    if spec.footer:
        ffont = _load_font(22)
        draw.text((_cx(spec.footer, ffont, draw), y1 - 38), spec.footer, font=ffont, fill=DIM_GREY)
