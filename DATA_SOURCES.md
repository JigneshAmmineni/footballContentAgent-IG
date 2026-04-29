# Data Sources — Auth & API Reference

Track all external sources, required credentials, and endpoint details here.
Add env vars to `.env.example` only — never commit real keys.

---

## football-data.org

**What it provides:** Fixtures, live/recent match results, league standings, top scorers — all Big 5 leagues (PL, La Liga, Bundesliga, Serie A, Ligue 1).

**Auth:** API key in request header `X-Auth-Token`.
**Env var:** `FOOTBALL_DATA_TOKEN`
**Register:** https://www.football-data.org/client/register

**Rate limit:** 10 requests/minute on free tier.
**Mitigation:** 7-second sleep between requests. Daily batch uses ~15 total requests.

**Key endpoints:**
```
GET /v4/competitions/{code}/matches?dateFrom=YYYY-MM-DD&dateTo=YYYY-MM-DD
    codes: PL, PD, BL1, SA, FL1

GET /v4/competitions/{code}/standings

GET /v4/competitions/{code}/scorers?limit=20
```

---

## NewsAPI.org

**What it provides:** Aggregated news from 150+ sports publishers. Covers injuries, transfers, quotes, match reactions.

**Auth:** API key as query param `apiKey`.
**Env var:** `NEWS_API_KEY`
**Register:** https://newsapi.org/register

**Rate limit:** 100 requests/day on free tier (Developer plan).
**Mitigation:** Max 5 queries per daily run. Use broad queries; avoid pagination.

**Example query:**
```
GET https://newsapi.org/v2/everything
  ?q=football+soccer+premier+league+bundesliga+ligue1+serie+a+laliga
  &language=en
  &sortBy=publishedAt
  &pageSize=50
  &apiKey={NEWS_API_KEY}
```

---

## Reddit r/soccer

**What it provides:** Viral news, transfer rumors, manager quotes surfaced by community upvotes.

**Auth:** None required. Public JSON endpoints.
**Env var:** None.

**Rate limit:** ~60 req/min for unauthenticated access.
**Mitigation:** Send a browser `User-Agent` header. Only 3 requests per run.

**Endpoints used:**
```
GET https://www.reddit.com/r/soccer/new.json?limit=50
GET https://www.reddit.com/r/soccer/hot.json?limit=50
GET https://www.reddit.com/r/soccer/rising.json?limit=25
```
**Headers required:**
```
User-Agent: Mozilla/5.0 (compatible; football-content-agent/1.0)
```

---

## FBref (via soccerdata)

**What it provides:** Deep per-player and per-team statistics — cumulative goals, assists, progressive carries, xG, etc. Used for stat comparisons and milestone detection.

**Auth:** None. Web scraping via `soccerdata` library.
**Env var:** None.
**Install:** `uv add soccerdata`

**Rate limit:** No hard limit, but FBref actively discourages bots.
**Mitigation:**
- `soccerdata` has a built-in 5-second delay between requests.
- Enable local file caching (default behavior) — data is re-used across runs and only re-fetched when stale.
- Do not run FBref fetchers more than once per day.

**Usage pattern:**
```python
import soccerdata as sd
fbref = sd.FBref(leagues=["ENG-Premier League", "ESP-La Liga", ...], seasons="2024-2025")
df = fbref.read_player_season_stats(stat_type="standard")
```

---

## Understat (via soccerdata)

**What it provides:** xG, xA, shot maps, match-level expected stats. Used for stat comparison posts.

**Auth:** None. Web scraping via `soccerdata` library.
**Env var:** None.

**Rate limit:** Same profile as FBref.
**Mitigation:** Same as FBref — soccerdata's built-in delay and local cache.

**Usage pattern:**
```python
import soccerdata as sd
understat = sd.Understat(leagues=["EPL", "La liga", "Bundesliga", "Serie A", "Ligue 1"])
df = understat.read_player_season_stats()
```

---

## RSS Feeds

**What they provide:** Match reports, injury news, transfer news, manager quotes, analysis.

**Auth:** None.
**Rate limit:** None.
**Library:** `feedparser`

| Outlet | Feed URL |
|---|---|
| BBC Sport Football | `https://feeds.bbci.co.uk/sport/football/rss.xml` |
| Sky Sports Football | `https://www.skysports.com/rss/12040` |
| Guardian Football | `https://www.theguardian.com/football/rss` |
| ESPN FC | `https://www.espn.com/espn/rss/soccer/news` |
| 90min | `https://www.90min.com/feed` |
| Goal.com | `https://www.goal.com/feeds/en/news` |

---

## .env.example additions

```
FOOTBALL_DATA_TOKEN=your_token_here
NEWS_API_KEY=your_key_here
```
