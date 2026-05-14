import hashlib
import logging

import feedparser
import requests

from app.models.raw_idea import RawIdea
from app.tools.fetchers.base import BaseFetcher

logger = logging.getLogger(__name__)

# feedparser.parse(url) uses urllib with no timeout — a slow feed could hang
# the entire pipeline indefinitely. Fetch bytes ourselves with a hard timeout
# and hand them to feedparser to parse offline.
_HTTP_TIMEOUT = 10
_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; football-content-agent/1.0)"}


class RssFetcher(BaseFetcher):
    """Fetches all configured RSS outlets in one pass."""

    def __init__(self, feeds: list):  # list[RssFeedConfig]
        self._feeds = feeds

    def fetch(self) -> list[RawIdea]:
        ideas: list[RawIdea] = []
        for feed_cfg in self._feeds:
            try:
                ideas.extend(self._fetch_one(feed_cfg.name, feed_cfg.url))
            except Exception as e:
                # Per-feed isolation: one slow/broken feed must not knock out
                # the other 5 outlets. Log and continue.
                logger.warning("rss feed %s failed: %s", feed_cfg.name, e)
        return ideas[:50]

    def _fetch_one(self, name: str, url: str) -> list[RawIdea]:
        resp = requests.get(url, headers=_HTTP_HEADERS, timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        ideas = []
        for entry in parsed.entries[:10]:  # cap per outlet to avoid flooding
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
