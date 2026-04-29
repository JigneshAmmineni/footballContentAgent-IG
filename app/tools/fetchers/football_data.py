import time
import hashlib
from datetime import date, timedelta

import requests

from app.models.raw_idea import RawIdea
from app.tools.fetchers.base import BaseFetcher

_BASE_URL = "https://api.football-data.org/v4"
_SLEEP_BETWEEN_CALLS = 7  # 10 req/min limit → safe at 7s


class FootballDataFetcher(BaseFetcher):
    def __init__(self, token: str, competitions: list[str]):
        self._headers = {"X-Auth-Token": token}
        self._competitions = competitions

    def fetch(self) -> list[RawIdea]:
        ideas: list[RawIdea] = []
        for code in self._competitions:
            ideas.extend(self._fetch_recent_matches(code))
            time.sleep(_SLEEP_BETWEEN_CALLS)
            ideas.extend(self._fetch_standings(code))
            time.sleep(_SLEEP_BETWEEN_CALLS)
            ideas.extend(self._fetch_scorers(code))
            time.sleep(_SLEEP_BETWEEN_CALLS)
        return ideas

    def _fetch_recent_matches(self, code: str) -> list[RawIdea]:
        today = date.today()
        date_from = (today - timedelta(days=2)).isoformat()
        date_to = today.isoformat()
        resp = requests.get(
            f"{_BASE_URL}/competitions/{code}/matches",
            headers=self._headers,
            params={"dateFrom": date_from, "dateTo": date_to},
            timeout=10,
        )
        resp.raise_for_status()
        matches = resp.json().get("matches", [])
        ideas = []
        for m in matches:
            if m.get("status") not in ("FINISHED", "IN_PLAY"):
                continue
            home = m["homeTeam"]["name"]
            away = m["awayTeam"]["name"]
            score = m.get("score", {}).get("fullTime", {})
            hint = f"{home} {score.get('home', '?')}–{score.get('away', '?')} {away} ({code})"
            ideas.append(RawIdea(
                id=_sha256(f"football_data:match:{m['id']}"),
                source="football_data",
                content_hint=hint,
                raw_data=m,
                suggested_type="match_result",
            ))
        return ideas

    def _fetch_standings(self, code: str) -> list[RawIdea]:
        resp = requests.get(
            f"{_BASE_URL}/competitions/{code}/standings",
            headers=self._headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        # Emit one idea covering the top/bottom of the table — useful for form + title race posts
        standings = data.get("standings", [{}])[0].get("table", [])
        if not standings:
            return []
        top3 = [t["team"]["name"] for t in standings[:3]]
        bot3 = [t["team"]["name"] for t in standings[-3:]]
        hint = f"{code} standings: top3={top3}, bottom3={bot3}"
        return [RawIdea(
            id=_sha256(f"football_data:standings:{code}:{date.today()}"),
            source="football_data",
            content_hint=hint,
            raw_data={"competition": code, "standings": standings},
            suggested_type="standings",
        )]

    def _fetch_scorers(self, code: str) -> list[RawIdea]:
        resp = requests.get(
            f"{_BASE_URL}/competitions/{code}/scorers",
            headers=self._headers,
            params={"limit": 10},
            timeout=10,
        )
        resp.raise_for_status()
        scorers = resp.json().get("scorers", [])
        ideas = []
        for s in scorers:
            player = s["player"]["name"]
            goals = s.get("goals", 0)
            team = s["team"]["name"]
            hint = f"{player} ({team}) has {goals} goals in {code} this season"
            ideas.append(RawIdea(
                id=_sha256(f"football_data:scorer:{code}:{player}:{goals}"),
                source="football_data",
                content_hint=hint,
                raw_data=s,
                suggested_type="milestone",
            ))
        return ideas


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
