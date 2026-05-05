from typing import Any
from pydantic import BaseModel


class EnrichedPost(BaseModel):
    idea_id: str
    content_direction: str
    data_needed: list[str]
    source_url: str | None
    priority: int
    article_text: str           # Jina Reader extract of source_url
    article_image_url: str | None = None  # reference image found in article
    match_stats: dict[str, Any] | None = None   # football-data.org match payload
    extra_stats: dict[str, Any] | None = None   # xG or other Understat/FBref data
