from enum import Enum


class GeneratorPath(str, Enum):
    PILLOW = "pillow"
    CHART = "chart"
    IMAGEN = "imagen"


_PILLOW_KEYWORDS = {
    "quote", "said", "press conference", "confirmed", "announce",
    "scored", "milestone", "hat-trick", "goal", "assist",
    "vs", "preview", "fixture", "kickoff", "kick-off",
    "result", "won", "drew", "lost", "defeat", "victory",
    "transfer", "sign", "injury", "debut", "form", "last 5",
}

_CHART_KEYWORDS = {
    "stat", "xg", "radar", "compared to", "comparison",
    "better than", "worse than", "ranking", "top scorer",
    "expected goals", "progressive", "per 90",
}


def route(content_direction: str) -> GeneratorPath:
    """Determine the image generation path from a free-form content_direction string.
    Uses keyword matching — deterministic, no LLM call.
    """
    lower = content_direction.lower()
    if any(kw in lower for kw in _CHART_KEYWORDS):
        return GeneratorPath.CHART
    if any(kw in lower for kw in _PILLOW_KEYWORDS):
        return GeneratorPath.PILLOW
    return GeneratorPath.IMAGEN
