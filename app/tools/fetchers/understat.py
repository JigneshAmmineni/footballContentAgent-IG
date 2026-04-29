import hashlib
import os
from pathlib import Path

from app.models.raw_idea import RawIdea
from app.tools.fetchers.base import BaseFetcher


class UnderstatFetcher(BaseFetcher):
    """Fetches xG and shot stats from Understat via soccerdata."""

    def __init__(self, leagues: list[str], season: str, cache_dir: Path):
        self._leagues = leagues
        self._season = season
        self._cache_dir = cache_dir

    def fetch(self) -> list[RawIdea]:
        try:
            import soccerdata as sd
        except ImportError:
            return []

        os.environ.setdefault("SOCCERDATA_DIR", str(self._cache_dir))
        ideas = []
        try:
            understat = sd.Understat(leagues=self._leagues, seasons=self._season)
            df = understat.read_player_season_stats()
            df = df.reset_index()
            for _, row in df.head(30).iterrows():
                player = str(row.get("player", "Unknown"))
                team = str(row.get("team", "Unknown"))
                xg = row.get("xG", 0)
                goals = row.get("goals", 0)
                hint = (
                    f"[Understat] {player} ({team}): {goals} goals vs "
                    f"{round(float(xg), 2) if xg == xg else 0} xG in {self._season}"
                )
                ideas.append(RawIdea(
                    id=_sha256(f"understat:{player}:{team}:{self._season}"),
                    source="understat",
                    content_hint=hint,
                    raw_data={
                        "player": player,
                        "team": team,
                        "goals": _safe(goals),
                        "xG": _safe(xg),
                        "season": self._season,
                        "stats": {k: _safe(v) for k, v in row.items()},
                    },
                    suggested_type="stat",
                ))
        except Exception:
            pass
        return ideas


def _safe(v):
    try:
        import math
        if v != v or (isinstance(v, float) and math.isinf(v)):
            return None
        return v.item() if hasattr(v, "item") else v
    except Exception:
        return str(v)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
