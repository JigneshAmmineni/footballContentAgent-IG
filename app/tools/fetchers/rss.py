import hashlib

import feedparser

from app.models.raw_idea import RawIdea
from app.tools.fetchers.base import BaseFetcher


class RssFetcher(BaseFetcher):
    """Fetches all configured RSS outlets in one pass."""

    def __init__(self, feeds: list):  # list[RssFeedConfig]
        self._feeds = feeds

    def fetch(self) -> list[RawIdea]:
        ideas: list[RawIdea] = []
        for feed_cfg in self._feeds:
            ideas.extend(self._fetch_one(feed_cfg.name, feed_cfg.url))
        return ideas

    def _fetch_one(self, name: str, url: str) -> list[RawIdea]:
        parsed = feedparser.parse(url)
        ideas = []
        for entry in parsed.entries[:20]:  # cap per outlet to avoid flooding
            title = entry.get("title", "")
            link = entry.get("link", "")
            summary = entry.get("summary", "")
            if not title:
                continue
            # Try to get the featured image from media tags
            image_url = _extract_image(entry)
            hint = f"[RSS:{name}] {title}"
            ideas.append(RawIdea(
                id=_sha256(f"rss:{name}:{link or title}"),
                source=f"rss:{name}",
                content_hint=hint,
                raw_data={
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "published": entry.get("published", ""),
                    "outlet": name,
                    "image_url": image_url,
                },
                suggested_type="news",
                source_url=link or None,
            ))
        return ideas


def _extract_image(entry) -> str | None:
    """Pull media:thumbnail or enclosure image from an RSS entry."""
    # media:thumbnail
    media_thumbnail = entry.get("media_thumbnail", [])
    if media_thumbnail:
        return media_thumbnail[0].get("url")
    # media:content
    media_content = entry.get("media_content", [])
    for m in media_content:
        if m.get("medium") == "image" or m.get("type", "").startswith("image"):
            return m.get("url")
    # enclosures
    for enc in entry.get("enclosures", []):
        if enc.get("type", "").startswith("image"):
            return enc.get("href")
    return None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
