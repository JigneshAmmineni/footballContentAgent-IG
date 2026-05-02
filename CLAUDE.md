# Project: Football Content Agent

## Python environment

All project Python scripts must be run with `.venv/Scripts/python`, not the system Python.
The `.venv` contains all project dependencies; the system Python does not.

```bash
# correct
.venv/Scripts/python scratch/dump_samples.py
.venv/Scripts/python -m pytest

# wrong — missing packages
python scratch/dump_samples.py
```

## API rate limits — stop and warn before triggering fetches

Before running any fetcher manually (dump_samples.py, full pipeline, or any script that calls fetch()), check how many times it has already been run today and warn if we're approaching the limit. When in doubt, ask before running.

| Fetcher | Limit | Notes |
|---|---|---|
| **football-data.org** (`FootballDataFetcher`) | **10 req/min** on free tier | Each `fetch()` call makes 3 req × 5 competitions = **15 requests**, sleeping 7s between each to stay under the per-minute cap. One full run takes ~3 min. Running it twice in quick succession risks a 429. |
| **NewsAPI** (`NewsApiFetcher`) | **100 req/day** on free tier (Developer plan) | Each `fetch()` makes exactly **1 request**. 100/day sounds safe but the comment in newsapi.py says "use conservatively" — treat the practical limit as ~5 runs/day to leave headroom. |
| **Reddit** (`RedditFetcher`) | ~**60 req/min** unauthenticated | Uses the public JSON API (no OAuth). Each `fetch()` makes **3 requests** (new/hot/rising). Very unlikely to hit this during normal testing. No daily cap, but repeated rapid calls risk a temporary IP block. |
| **RSS feeds** (`RssFetcher`) | No hard limit | Polls 6 feeds (BBC, Sky, Guardian, ESPN, 90min, Goal). Each `fetch()` makes **6 HTTP requests**. These are public feeds — no API key, no quota. Safe to run freely. |
| **FBref** (`FbrefFetcher`) | Scraping — polite use only | Scrapes football-reference.com via `soccerdata`. Results are cached locally in `soccerdata_cache/`. **Only run once per session** — the cache prevents re-scraping. Hammering it risks an IP ban. |
| **Understat** (`UnderstatFetcher`) | Scraping — polite use only | Same as FBref. Cached locally. **Only run once per session.** |

## Scratch pipeline files

| File | Stage | Contents |
|---|---|---|
| `scratch/samples.json` | Fetcher output / judge input | Top 100 RSS ideas fetched from all configured feeds |
| `scratch/candidates.json` | Judge output / ranker input | Ideas approved by the judge (~25), enriched with `content_hint` and `fetched_at` |
| `scratch/approved.json` | Ranker output | Top N stories from candidates, ranked in order of importance (highest priority first) |

To re-run only the ranker against the existing candidates (e.g. after prompt tuning):
```bash
.venv/Scripts/python scratch/run_judge.py --ranker-only
```

### Safe testing pattern
- `dump_samples.py --source reddit` or `--source rss` — free to run as often as needed
- `dump_samples.py --source football_data` — max 2–3× per day, never back-to-back
- `dump_samples.py --source newsapi` — max ~5× per day
- `dump_samples.py` (fast/all) — max 2× per day due to NewsAPI and football-data combined
- Full pipeline (`adk run`) — counts as one fetch of all sources; treat as 1 of your ~2 daily runs
