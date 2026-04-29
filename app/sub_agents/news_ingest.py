import asyncio
import json
import logging
import os
from pathlib import Path

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai import types as genai_types

from app.config import config
from app.tools.dedup import dedup
from app.tools.fetchers import (
    FootballDataFetcher,
    FbrefFetcher,
    NewsApiFetcher,
    RedditFetcher,
    RssFetcher,
    UnderstatFetcher,
)

logger = logging.getLogger(__name__)

_DEBUG_DUMP = Path(__file__).parent.parent.parent / "scratch" / "last_raw_ideas.json"


def _build_fetchers():
    fetchers = []
    try:
        fetchers.append(FootballDataFetcher(config.football_data_token(), config.competitions))
    except EnvironmentError:
        logger.warning("FOOTBALL_DATA_TOKEN not set — skipping FootballDataFetcher")
    try:
        fetchers.append(NewsApiFetcher(config.news_api_key()))
    except EnvironmentError:
        logger.warning("NEWS_API_KEY not set — skipping NewsApiFetcher")
    fetchers.append(RedditFetcher())
    fetchers.append(RssFetcher(config.rss_feeds))
    if os.getenv("ENABLE_SLOW_FETCHERS", "false").lower() == "true":
        fetchers.append(FbrefFetcher(config.fbref_leagues, config.current_season, config.soccerdata_cache_dir))
        fetchers.append(UnderstatFetcher(config.understat_leagues, config.current_season, config.soccerdata_cache_dir))
    return fetchers


class NewsIngestAgent(BaseAgent):
    """Runs all data fetchers concurrently, deduplicates results, writes to state."""

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._fetchers = _build_fetchers()
        logger.info("NewsIngestAgent initialised with %d fetchers: %s",
                    len(self._fetchers), [type(f).__name__ for f in self._fetchers])

    async def _run_async_impl(self, ctx: InvocationContext):
        logger.info("NewsIngestAgent starting — fetching from %d sources", len(self._fetchers))
        all_ideas = []

        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(None, f.fetch) for f in self._fetchers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for fetcher, result in zip(self._fetchers, results):
            name = type(fetcher).__name__
            if isinstance(result, Exception):
                logger.error("Fetcher %s FAILED: %s", name, result)
            else:
                logger.info("Fetcher %s returned %d ideas", name, len(result))
                all_ideas.extend(result)

        logger.info("Total ideas before dedup: %d", len(all_ideas))

        config.seen_file.parent.mkdir(parents=True, exist_ok=True)
        unique = dedup(all_ideas, config.seen_file)

        logger.info("After dedup: %d unique ideas (dropped %d)", len(unique), len(all_ideas) - len(unique))

        serialised = [i.model_dump(mode="json") for i in unique]
        ctx.session.state["raw_ideas"] = serialised

        # Debug dump — always written so offline inspection is possible
        _DEBUG_DUMP.parent.mkdir(parents=True, exist_ok=True)
        _DEBUG_DUMP.write_text(
            json.dumps(serialised, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("Debug dump written to %s", _DEBUG_DUMP)

        yield Event(
            author=self.name,
            content=genai_types.Content(
                parts=[genai_types.Part(
                    text=(
                        f"Ingested {len(unique)} unique ideas "
                        f"from {len(self._fetchers)} sources "
                        f"({len(all_ideas)} total before dedup)."
                    )
                )]
            ),
        )
