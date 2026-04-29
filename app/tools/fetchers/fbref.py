import hashlib
import os
from pathlib import Path

from app.models.raw_idea import RawIdea
from app.tools.fetchers.base import BaseFetcher


class FbrefFetcher(BaseFetcher):
    """Fetches player season stats from FBref via soccerdata.
    Uses local file cache to avoid repeat scraping.
    """

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
            fbref = sd.FBref(leagues=self._leagues, seasons=self._season)
            df = fbref.read_player_season_stats(stat_type="standard")
            df = df.reset_index()
            for _, row in df.head(50).iterrows():  # top 50 rows as stat ideas
                player = str(row.get("player", "Unknown"))
                team = str(row.get("team", "Unknown"))
                goals = row.get("goals", 0)
                assists = row.get("assists", 0)
                hint = (
                    f"[FBref] {player} ({team}): {goals} goals, {assists} assists "
                    f"in {self._season}"
                )
                ideas.append(RawIdea(
                    id=_sha256(f"fbref:{player}:{team}:{self._season}"),
                    source="fbref",
                    content_hint=hint,
                    raw_data={
                        "player": player,
                        "team": team,
                        "goals": int(goals) if goals == goals else 0,
                        "assists": int(assists) if assists == assists else 0,
                        "season": self._season,
                        "stats": {k: _safe(v) for k, v in row.items()},
                    },
                    suggested_type="stat",
                ))
        except Exception:
            pass  # FBref scraping may fail transiently; non-fatal
        return ideas


def _safe(v):
    """Convert pandas values to JSON-serializable types."""
    try:
        import math
        if v != v or (isinstance(v, float) and math.isinf(v)):
            return None
        return v.item() if hasattr(v, "item") else v
    except Exception:
        return str(v)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
