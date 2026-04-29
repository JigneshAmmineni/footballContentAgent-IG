import hashlib
from datetime import date, timedelta

import requests

from app.models.raw_idea import RawIdea
from app.tools.fetchers.base import BaseFetcher

_BASE_URL = "https://newsapi.org/v2/everything"
# Max 5 queries/day on free tier (100 req/day, use conservatively)
_QUERY = (
    "football soccer "
    "(premier league OR bundesliga OR ligue 1 OR serie a OR la liga) "
    "-fantasy -betting -odds"
)


class NewsApiFetcher(BaseFetcher):
    def __init__(self, api_key: str):
        self._api_key = api_key

    def fetch(self) -> list[RawIdea]:
        from_date = (date.today() - timedelta(days=2)).isoformat()
        resp = requests.get(
            _BASE_URL,
            params={
                "q": _QUERY,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 50,  # single page, no pagination
                "from": from_date,
                "apiKey": self._api_key,
            },
            timeout=15,
        )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        ideas = []
        for a in articles:
            url = a.get("url", "")
            title = a.get("title", "")
            if not title:
                continue
            hint = f"[NewsAPI] {title}"
            ideas.append(RawIdea(
                id=_sha256(f"newsapi:{url}"),
                source="newsapi",
                content_hint=hint,
                raw_data={
                    "title": title,
                    "description": a.get("description", ""),
                    "publishedAt": a.get("publishedAt", ""),
                    "source": a.get("source", {}).get("name", ""),
                    "url": url,
                },
                suggested_type="news",
                source_url=url or None,
            ))
        return ideas


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
