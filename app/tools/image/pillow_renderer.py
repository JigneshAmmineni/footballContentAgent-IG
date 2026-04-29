from pathlib import Path

from PIL import Image, ImageDraw

from app.tools.image.composite import Overlay, composite

_CANVAS = (1080, 1080)
_TEXT_X = 90  # left margin for main text
_TEXT_Y_MAIN = 680  # y-start for main text in gradient zone
_TEXT_Y_SOURCE = 1010  # y for source credit strip
_SOURCE_FONT_SIZE = 28
_MAIN_FONT_SIZE = 72
_BADGE_SIZE = (80, 80)


def render_quote_card(
    background: Image.Image,
    quote: str,
    speaker: str,
    output_path: Path,
) -> Path:
    overlays = [
        Overlay(
            text=f'"{quote}"',
            position=(_TEXT_X, _TEXT_Y_MAIN - 60),
            font_size=_MAIN_FONT_SIZE,
            max_width=900,
        ),
        Overlay(
            text=f"— {speaker}",
            position=(_TEXT_X, _TEXT_Y_MAIN + 180),
            font_size=40,
            color=(220, 220, 220, 230),
        ),
    ]
    return composite(background, None, overlays, output_path)


def render_milestone_card(
    background: Image.Image,
    headline: str,
    subtext: str,
    output_path: Path,
) -> Path:
    overlays = [
        Overlay(
            text=headline,
            position=(_TEXT_X, _TEXT_Y_MAIN),
            font_size=_MAIN_FONT_SIZE,
            max_width=900,
        ),
        Overlay(
            text=subtext,
            position=(_TEXT_X, _TEXT_Y_MAIN + 200),
            font_size=38,
            color=(220, 220, 220, 220),
        ),
    ]
    return composite(background, None, overlays, output_path)


def render_match_card(
    home_badge: Image.Image | None,
    away_badge: Image.Image | None,
    home_name: str,
    away_name: str,
    score: str,  # e.g. "2 – 1" or "vs" for preview
    competition: str,
    output_path: Path,
) -> Path:
    background = _dark_background()
    content_zone = _build_match_graphic(
        home_badge, away_badge, home_name, away_name, score, competition
    )
    return composite(background, content_zone, [], output_path)


def render_form_dots(
    teams: list[dict],  # [{"name": str, "form": ["W","D","L","W","W"]}]
    output_path: Path,
) -> Path:
    img = Image.new("RGBA", _CANVAS, (18, 18, 28, 255))
    draw = ImageDraw.Draw(img)
    dot_r = 22
    row_h = 90
    start_y = 200
    for i, team in enumerate(teams[:6]):
        y = start_y + i * row_h
        draw.text((60, y + 10), team["name"], fill=(255, 255, 255, 230))
        for j, result in enumerate(team["form"][:5]):
            cx = 500 + j * (dot_r * 2 + 14)
            cy = y + dot_r
            color = _form_color(result)
            draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=color)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(output_path, format="PNG")
    return output_path


def _form_color(result: str) -> tuple[int, int, int, int]:
    return {"W": (34, 197, 94, 255), "D": (234, 179, 8, 255), "L": (239, 68, 68, 255)}.get(
        result.upper(), (100, 100, 100, 255)
    )


def _dark_background() -> Image.Image:
    return Image.new("RGB", _CANVAS, (18, 18, 28))


def _build_match_graphic(home_b, away_b, home, away, score, competition) -> Image.Image:
    img = Image.new("RGBA", (_CANVAS[0], 600), (18, 18, 28, 0))
    draw = ImageDraw.Draw(img)
    # Paste badges if available
    if home_b:
        img.paste(home_b.resize(_BADGE_SIZE, Image.LANCZOS), (120, 240), home_b.convert("RGBA"))
    if away_b:
        img.paste(away_b.resize(_BADGE_SIZE, Image.LANCZOS), (880, 240), away_b.convert("RGBA"))
    # Team names
    draw.text((160, 340), home, fill=(255, 255, 255, 230))
    draw.text((880, 340), away, fill=(255, 255, 255, 230))
    # Score / vs
    draw.text((490, 260), score, fill=(255, 255, 255, 255))
    draw.text((480, 160), competition, fill=(180, 180, 180, 200))
    return img
