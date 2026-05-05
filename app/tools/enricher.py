"""Enriches an ApprovedIdea with article text (Jina Reader) and structured
match stats (football-data.org), based on the idea's data_needed list."""
import re
import requests

from app.models.approved_idea import ApprovedIdea
from app.models.enriched_post import EnrichedPost

_JINA_BASE = "https://r.jina.ai/"
_FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"
_JINA_TIMEOUT = 20
_FD_TIMEOUT = 10

# Keywords in data_needed that trigger a football-data.org fetch
_MATCH_STAT_KEYWORDS = {"match stats", "match statistics", "match data", "goal highlights", "xg", "scorers"}


def enrich(idea: ApprovedIdea, football_data_token: str | None = None) -> EnrichedPost:
    article_text, article_image_url = _fetch_article(idea.source_url)
    match_stats = None

    needs_match_stats = any(
        kw in item.lower()
        for item in idea.data_needed
        for kw in _MATCH_STAT_KEYWORDS
    )
    if needs_match_stats and football_data_token:
        match_stats = _find_match_stats(article_text, football_data_token)

    return EnrichedPost(
        idea_id=idea.raw_idea_id,
        content_direction=idea.content_direction,
        data_needed=idea.data_needed,
        source_url=idea.source_url,
        priority=idea.priority,
        article_text=article_text,
        article_image_url=article_image_url,
        match_stats=match_stats,
    )


def _fetch_article(url: str | None) -> tuple[str, str | None]:
    if not url:
        return "", None
    try:
        resp = requests.get(
            f"{_JINA_BASE}{url}",
            headers={"Accept": "text/plain", "X-Return-Format": "text"},
            timeout=_JINA_TIMEOUT,
        )
        resp.raise_for_status()
        text = resp.text
        # Treat very short responses as a failed fetch (Cloudflare block, redirect pages, etc.)
        if len(text.strip()) < 300:
            print(f"  Jina Reader returned too-short response ({len(text)} chars) for {url} -- treating as failed")
            return "", None
        image_url = _extract_first_image_url(text)
        return text, image_url
    except Exception as e:
        print(f"  Jina Reader failed for {url}: {e}")
        return "", None


def _extract_first_image_url(text: str) -> str | None:
    # Jina markdown output: ![alt](url) or plain https://...jpg/png/webp
    md_match = re.search(r"!\[.*?\]\((https?://[^\s)]+)\)", text)
    if md_match:
        return md_match.group(1)
    url_match = re.search(r"https?://\S+\.(?:jpg|jpeg|png|webp)(?:\?\S*)?", text, re.IGNORECASE)
    if url_match:
        return url_match.group(0)
    return None


def _find_match_stats(article_text: str, token: str) -> dict | None:
    """Try to identify teams from article text and fetch match from football-data.org."""
    teams = _extract_team_names(article_text)
    if len(teams) < 2:
        return None

    headers = {"X-Auth-Token": token}
    # Search UCL + major competitions for a recent match involving these teams
    for competition in ["CL", "EL", "PL", "PD", "BL1", "SA", "FL1"]:
        try:
            resp = requests.get(
                f"{_FOOTBALL_DATA_BASE}/competitions/{competition}/matches",
                headers=headers,
                params={"status": "FINISHED", "limit": 20},
                timeout=_FD_TIMEOUT,
            )
            if resp.status_code != 200:
                continue
            for match in resp.json().get("matches", []):
                home = match.get("homeTeam", {}).get("name", "").lower()
                away = match.get("awayTeam", {}).get("name", "").lower()
                if any(t in home for t in teams) and any(t in away for t in teams):
                    return match
                if any(t in away for t in teams) and any(t in home for t in teams):
                    return match
        except Exception:
            continue
    return None


# Rough list of Big 5 + UCL club name fragments for team extraction
_CLUB_FRAGMENTS = [
    "psg", "paris", "bayern", "munich", "arsenal", "liverpool", "manchester",
    "united", "city", "chelsea", "tottenham", "spurs", "barcelona", "real madrid",
    "atletico", "juventus", "inter", "milan", "dortmund", "ajax", "benfica",
    "porto", "napoli", "roma", "lazio", "sevilla", "villarreal", "leicester",
    "nottingham", "forest", "villa", "newcastle", "west ham", "crystal palace",
    "brentford", "fulham", "wolves", "everton", "leeds", "burnley", "ipswich",
]


def _extract_team_names(text: str) -> list[str]:
    lower = text.lower()
    found = [frag for frag in _CLUB_FRAGMENTS if frag in lower]
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique = []
    for f in found:
        if f not in seen:
            seen.add(f)
            unique.append(f)
    return unique[:4]  # cap to avoid over-fetching
