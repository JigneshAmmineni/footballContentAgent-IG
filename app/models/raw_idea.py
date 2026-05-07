from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field


class RawIdea(BaseModel):
    id: str  # SHA-256 of (source + content_fingerprint)
    source: str  # "football_data" | "newsapi" | "reddit" | "rss:{outlet}"
    content_hint: str  # short natural-language summary of the event/data point
    raw_data: dict[str, Any]  # original payload from source
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    suggested_type: str | None = None  # non-binding hint from fetcher
    source_url: str | None = None  # article URL for Jina Reader image sourcing


class RawIdeaList(BaseModel):
    ideas: list[RawIdea]
