"""Standalone script — fetches raw ideas and dumps to scratch/samples.json.
Used for iterating prompts in AI Studio without running the full pipeline.

Usage:
    python scratch/dump_samples.py
    python scratch/dump_samples.py --source football_data
    python scratch/dump_samples.py --limit 10
"""
import argparse
import json
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from app.config import config
from app.tools.fetchers import (
    FootballDataFetcher,
    FbrefFetcher,
    NewsApiFetcher,
    RedditFetcher,
    RssFetcher,
    UnderstatFetcher,
)


def main():
    parser = argparse.ArgumentParser(description="Dump raw ideas to scratch/samples.json")
    parser.add_argument("--source", default="fast", help="Source to fetch (fast, all, football_data, newsapi, reddit, rss, fbref, understat). 'fast' skips fbref/understat (they need a local browser).")
    parser.add_argument("--limit", type=int, default=30, help="Max ideas to dump")
    args = parser.parse_args()

    fetchers = {
        "football_data": lambda: FootballDataFetcher(config.football_data_token(), config.competitions),
        "newsapi": lambda: NewsApiFetcher(config.news_api_key()),
        "reddit": lambda: RedditFetcher(),
        "rss": lambda: RssFetcher(config.rss_feeds),
        "fbref": lambda: FbrefFetcher(config.fbref_leagues, config.current_season, config.soccerdata_cache_dir),
        "understat": lambda: UnderstatFetcher(config.understat_leagues, config.current_season, config.soccerdata_cache_dir),
    }

    fast_sources = ["football_data", "newsapi", "reddit", "rss"]
    if args.source == "all":
        active = list(fetchers.keys())
    elif args.source == "fast":
        active = fast_sources
    else:
        active = [args.source]

    ideas = []
    for name in active:
        print(f"Fetching {name}...", flush=True)
        try:
            fetcher = fetchers[name]()
            batch = fetcher.fetch()
            print(f"  -> {len(batch)} ideas")
            ideas.extend(batch)
        except Exception as e:
            print(f"  FAILED {name}: {e}")

    ideas = ideas[: args.limit]
    out_path = Path(__file__).parent / "samples.json"
    out_path.write_text(
        json.dumps([i.model_dump(mode="json") for i in ideas], indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\nDumped {len(ideas)} ideas -> {out_path}")


if __name__ == "__main__":
    main()
