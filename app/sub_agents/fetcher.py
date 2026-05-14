"""FetcherAgent — runs the four fast-source fetchers (football_data, newsapi,
reddit, rss), deduplicates, and writes the result to session state.

Outputs to state:
  raw_ideas:       list[dict]  (RawIdea.model_dump for downstream Python access)
  raw_ideas_json:  str         (JSON string for the idea_judge prompt placeholder)
"""
from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions

from app.config import config
from app.models.raw_idea import RawIdea
from app.tools.dedup import dedup
from app.tools.fetchers import (
    FootballDataFetcher,
    NewsApiFetcher,
    RedditFetcher,
    RssFetcher,
)

logger = logging.getLogger(__name__)

# Per-source caps so one chatty source can't drown out the others.
_SOURCE_CAPS = {"rss": 50, "reddit": 45, "newsapi": 30, "football_data": 30}


class FetcherAgent(BaseAgent):
    """Custom agent that fetches raw ideas from the four fast sources and dedups."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        ideas: list[RawIdea] = []

        for name, factory in self._build_fetchers().items():
            try:
                fetcher = factory()
                batch = fetcher.fetch()
            except Exception as e:
                # A single source failing must not kill the run — others may still produce.
                logger.warning("fetcher %s failed: %s", name, e)
                continue
            cap = _SOURCE_CAPS.get(name, 30)
            ideas.extend(batch[:cap])
            logger.info("fetcher %s: %d ideas (capped at %d)", name, len(batch), cap)

        # Cross-source semantic dedup + persistent seen.json filter.
        try:
            deduped = dedup(ideas, config.seen_file)
        except Exception as e:
            # Dedup is best-effort; if seen.json is corrupt, fall back to no-dedup.
            logger.warning("dedup failed (%s); passing all ideas to judge", e)
            deduped = ideas

        raw_ideas_payload = [i.model_dump(mode="json") for i in deduped]
        raw_ideas_json = json.dumps(raw_ideas_payload, indent=2, default=str)

        # Yield a single state-mutation event so the SequentialAgent's next
        # sub-agent (idea_judge) sees the populated state.
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            actions=EventActions(
                state_delta={
                    "raw_ideas": raw_ideas_payload,
                    "raw_ideas_json": raw_ideas_json,
                }
            ),
        )

    @staticmethod
    def _build_fetchers():
        # Lazily construct so missing API tokens fail at run time (per source),
        # not at import time.
        return {
            "football_data": lambda: FootballDataFetcher(
                config.football_data_token(), config.competitions
            ),
            "newsapi": lambda: NewsApiFetcher(config.news_api_key()),
            "reddit": lambda: RedditFetcher(),
            "rss": lambda: RssFetcher(config.rss_feeds),
        }


fetcher_agent = FetcherAgent(name="fetcher_agent")
