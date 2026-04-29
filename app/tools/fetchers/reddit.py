import hashlib

import requests

from app.models.raw_idea import RawIdea
from app.tools.fetchers.base import BaseFetcher

_SUBREDDIT = "soccer"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; football-content-agent/1.0)"}
_ENDPOINTS = ["new", "hot", "rising"]
_LIMIT = 50


class RedditFetcher(BaseFetcher):
    def fetch(self) -> list[RawIdea]:
        ideas: list[RawIdea] = []
        for endpoint in _ENDPOINTS:
            url = f"https://www.reddit.com/r/{_SUBREDDIT}/{endpoint}.json?limit={_LIMIT}"
            resp = requests.get(url, headers=_HEADERS, timeout=10)
            resp.raise_for_status()
            posts = resp.json().get("data", {}).get("children", [])
            for post in posts:
                d = post.get("data", {})
                title = d.get("title", "")
                post_url = d.get("url", "")
                permalink = f"https://reddit.com{d.get('permalink', '')}"
                upvotes = d.get("ups", 0)
                if not title:
                    continue
                hint = f"[Reddit/{endpoint}] {title} ({upvotes} upvotes)"
                ideas.append(RawIdea(
                    id=_sha256(f"reddit:{d.get('id', title)}"),
                    source="reddit",
                    content_hint=hint,
                    raw_data={
                        "title": title,
                        "upvotes": upvotes,
                        "url": post_url,
                        "permalink": permalink,
                        "flair": d.get("link_flair_text", ""),
                        "endpoint": endpoint,
                    },
                    suggested_type="news",
                    source_url=post_url if post_url.startswith("http") else permalink,
                ))
        return ideas


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
