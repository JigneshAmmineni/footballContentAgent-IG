import re
import urllib.request
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

from app.tools.image.imagen_client import generate_imagen

_JINA_BASE = "https://r.jina.ai/"
_OG_IMAGE_PATTERN = re.compile(r'!\[.*?\]\((https?://[^\s)]+)\)', re.IGNORECASE)
_TIMEOUT = 10


def get_background_image(
    source_url: str | None,
    content_direction: str,
    size: tuple[int, int] = (1080, 1080),
) -> Image.Image:
    """Return a PIL Image suitable for use as a post background.

    Tries Jina Reader to extract og:image from source_url first.
    Falls back to Gemini Imagen with a context-aware prompt.
    """
    if source_url:
        img = _try_jina(source_url, size)
        if img is not None:
            return img
    return _imagen_fallback(content_direction, size)


def _try_jina(url: str, size: tuple[int, int]) -> Image.Image | None:
    try:
        resp = requests.get(f"{_JINA_BASE}{url}", timeout=_TIMEOUT)
        if resp.status_code != 200:
            return None
        # Jina returns markdown — find first image URL
        matches = _OG_IMAGE_PATTERN.findall(resp.text)
        if not matches:
            return None
        img_url = matches[0]
        return _download_image(img_url, size)
    except Exception:
        return None


def _download_image(url: str, size: tuple[int, int]) -> Image.Image | None:
    try:
        resp = requests.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        return img.resize(size, Image.LANCZOS)
    except Exception:
        return None


def _imagen_fallback(content_direction: str, size: tuple[int, int]) -> Image.Image:
    prompt = _build_imagen_prompt(content_direction)
    return generate_imagen(prompt, size)


def _build_imagen_prompt(content_direction: str) -> str:
    lower = content_direction.lower()
    if any(w in lower for w in ("goal", "scored", "hat-trick", "milestone")):
        return (
            "Dramatic sports photography, professional footballer shooting the ball "
            "mid-kick, motion blur on ball, stadium crowd in background, floodlights, "
            "cinematic angle, high contrast"
        )
    if any(w in lower for w in ("transfer", "sign", "new club", "joining")):
        return (
            "Professional footballer in celebratory pose, training ground setting, "
            "bright natural light, confident expression, sports photography"
        )
    if any(w in lower for w in ("injury", "injured", "fitness")):
        return (
            "Footballer on the sidelines, physio or medical staff nearby, "
            "contemplative expression, out-of-focus stadium background, "
            "documentary sports photography style"
        )
    if any(w in lower for w in ("press conference", "said", "quote", "manager")):
        return (
            "Manager or player at press conference podium, microphones, press backdrop, "
            "professional sports photography, serious expression"
        )
    if any(w in lower for w in ("preview", "vs", "fixture", "kickoff")):
        return (
            "Two sets of passionate football fans in a stadium, rival atmosphere, "
            "floodlights, wide-angle lens, electric atmosphere, sports photography"
        )
    if any(w in lower for w in ("stat", "xg", "comparison", "radar")):
        return (
            "Abstract data visualization aesthetic, top-down aerial view of a football "
            "pitch, geometric lines, dark blue and gold color scheme, dramatic lighting"
        )
    return (
        "Dramatic football stadium atmosphere at night, floodlights, roaring crowd, "
        "wide angle, cinematic, sports photography"
    )
