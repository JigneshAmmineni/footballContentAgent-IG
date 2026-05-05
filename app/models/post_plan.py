from pydantic import BaseModel
from app.models.overlay_spec import OverlaySpec


class PostPlan(BaseModel):
    overlay_spec: OverlaySpec
    image_prompt: str  # cinematic background prompt for gpt-image-2 — no text, no logos
