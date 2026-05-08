# Football Content Agent

An autonomous multi-agent pipeline that publishes daily football content to Instagram. Every morning it fetches stories from four sources, judges and ranks ideas with Gemini, generates graphic images with gpt-image-2, writes captions, and publishes — without human involvement.

---

## How It Works

```
Cloud Scheduler (7 AM ET)
        │
        ▼
Vertex AI Agent Engine  ──── HTTP POST /query ────▶  FootballPipelineApp
        │
        ▼
  root_agent (SequentialAgent)
        │
        ├─ 1. fetcher_agent         ← aggregates ~120 ideas from 4 sources
        │
        ├─ 2. idea_judge_agent      ← filters to ~25 quality candidates
        │
        ├─ 3. idea_ranker_agent     ← selects & ranks top 5
        │
        ├─ 4. content_generator_agent  ← generates image + caption per idea
        │         │
        │         ├─ researcher_agent    (per-idea, conditional)
        │         ├─ content_planner_agent  (per-idea)
        │         └─ caption_writer_agent   (per-idea)
        │
        └─ 5. publisher_agent       ← uploads to GCS, posts to Instagram
```

---

## Agent Architecture

### Root Orchestrator

| Agent | Type | Role |
|---|---|---|
| `root_agent` | `SequentialAgent` | Runs all 5 pipeline stages in order; passes session state between them |

### Pipeline Stages

| Agent | Type | Model | What It Does |
|---|---|---|---|
| `fetcher_agent` | `BaseAgent` | — | Pulls ideas from football-data.org, NewsAPI, Reddit, and 5 RSS feeds. Deduplicates cross-source with `seen.json`. Caps each source at 30 ideas. |
| `idea_judge_agent` | `LlmAgent` | gemini-2.5-pro | Reads all raw ideas, filters to ~25 that are visually interesting and data-rich. Adds `content_direction` and `data_needed` hints for downstream agents. |
| `idea_ranker_agent` | `LlmAgent` | gemini-2.5-pro | Ranks the 25 candidates by newsworthiness and visual potential. Outputs the top 5 with priority scores 1–10. |
| `content_generator_agent` | `BaseAgent` | — | Orchestrates a 5-step per-idea loop: enrich → research → plan → generate image → write caption. Writes `final_posts` to session state when all 5 are done. |
| `publisher_agent` | `BaseAgent` | — | For each post: converts PNG → JPEG, crops to Instagram's 4:5 ratio, uploads to GCS, publishes via the Graph API. |

### Content Generator Sub-Agents (per idea)

| Agent | Type | Model | Triggered When | Output |
|---|---|---|---|---|
| `researcher_agent` | `LlmAgent` | gemini-2.5-flash | Article text < 800 chars or `data_needed` flags are set | Enriched article facts via Google Search |
| `content_planner_agent` | `LlmAgent` | gemini-2.5-pro | Always | `PostPlan`: layout type, overlay text fields, image prompt for gpt-image-2 |
| `caption_writer_agent` | `LlmAgent` | gemini-2.5-flash | Always | Instagram caption + hashtags |

---

## Multi-Agent Design Patterns

### 1. Sequential Pipeline with Shared State
`root_agent` is a `SequentialAgent` — each stage reads from and writes to `session.state`. No agent knows about the others; they communicate purely through named state keys.

```
fetcher  →  raw_ideas_json
judge    →  candidate_ideas_json
ranker   →  approved_ideas
generator →  final_posts
publisher →  published_posts
```

### 2. Nested Agent Invocation
`content_generator_agent` is a `BaseAgent` that runs its own inner agents per idea using `async for event in agent.run_async(ctx)`. This lets it loop over 5 ideas while the outer SequentialAgent sees a single stage.

```python
# content_generator iterates ideas, calling nested agents for each
for idea in approved_ideas:
    async for event in researcher_agent.run_async(ctx): ...
    async for event in content_planner_agent.run_async(ctx): ...
    async for event in caption_writer_agent.run_async(ctx): ...
```

### 3. Conditional Agent Activation
The researcher only fires when content is insufficient — checked at runtime inside `content_generator_agent`. This avoids unnecessary LLM calls on stories that already have rich article text.

```
if len(article_text) < 800 or idea.data_needed:
    run researcher_agent
```

### 4. Per-Source and Per-Idea Fault Isolation
Failures are scoped: one bad RSS feed doesn't stop the fetch stage, and one failed idea doesn't abort content generation. Each has its own `try/except` boundary with a logged warning and graceful continuation.

### 5. Structured Output with Retry
`content_planner_agent` produces a `PostPlan` Pydantic model. If Gemini returns malformed JSON (an intermittent failure), `content_generator_agent` retries up to 3 times with a 5-second backoff before failing that idea.

### 6. Callback-Based State Transformation
An `after_agent_callback` on `idea_judge_agent` converts its dict output to a JSON string for injection into the ranker's prompt. This decouples structured model output from prompt formatting.

---

## Session State Data Flow

```
Stage              State Key               Type
─────────────────────────────────────────────────────────────
fetcher_agent   → raw_ideas_json           str (JSON)
                  raw_ideas                list[dict]

idea_judge      → candidate_ideas_json     str (JSON)
                  candidate_ideas          dict

idea_ranker     → approved_ideas           dict

content_generator (per-idea loop):
                  researcher_query         str
                  enriched_post_json       str (JSON)
                  post_plan                dict (PostPlan)
                  caption_input_json       str (JSON)
                  caption_output           dict

                → final_posts              list[dict] (FinalPost)

publisher_agent → published_posts         list[dict]
                  (gcs_url + instagram_media_id per post)
```

---

## Data Sources

| Source | Fetcher | Ideas/Run | Notes |
|---|---|---|---|
| football-data.org | `FootballDataFetcher` | up to 30 | Match results & standings for PL, La Liga, Bundesliga, Serie A, Ligue 1. 15 req at 7s intervals (~3 min). |
| NewsAPI | `NewsApiFetcher` | up to 30 | Big-5 league news headlines. 1 request. 100 req/day limit. |
| Reddit r/soccer | `RedditFetcher` | up to 30 | Public JSON API (new/hot/rising). Occasionally 403s — handled gracefully. |
| RSS feeds | `RssFetcher` | up to 30 | BBC Sport, Sky Sports, The Guardian, ESPN, 90min. No auth, no quota. |

---

## Tools

| Tool | Used By | What It Does |
|---|---|---|
| `dedup.py` | fetcher_agent | Removes seen idea IDs and semantic near-duplicates (SequenceMatcher ≥ 0.82). Persists to `data/seen.json` locally or `dedup/seen.json` in GCS on Agent Engine. |
| `enricher.py` | content_generator | Fetches article text via Jina Reader. Pulls match stats from football-data.org when `data_needed` is set. Returns `EnrichedPost`. |
| `compositor.py` | content_generator | PIL-based renderer. Composites gpt-image-2 background with text overlays. Supports 4 layout types: `score_card`, `player_card`, `table_card`, `quote_card`. |
| `gcs.py` | publisher_agent | Converts PNG → JPEG, center-crops to 4:5 Instagram portrait ratio, uploads to GCS with public ACL. Returns the HTTPS URL. |
| `instagram.py` | publisher_agent | Instagram Graph API wrapper. Creates media container, polls publish status (up to 120s), publishes. Returns `media_id`. |

---

## Models

| Model | Used For | Why |
|---|---|---|
| `gemini-2.5-pro` | Judge, ranker, content planner | Deep reasoning for filtering, ranking, and structured layout planning |
| `gemini-2.5-flash` | Researcher, caption writer | Fast + cheap for search retrieval and short-form copy |
| `gpt-image-2` | Background image generation | Cinematic 1024×1536 sports graphics |

---

## Infrastructure (GCP)

```
Cloud Scheduler ──── HTTP POST ──▶ Vertex AI Agent Engine
                                          │
                          ┌───────────────┼───────────────┐
                          ▼               ▼               ▼
                   Secret Manager    Cloud Storage     Vertex AI
                   (API keys &       (images bucket:   (Gemini models
                    tokens)           posts/ + dedup/)  via Vertex API)
```

| Service | Purpose |
|---|---|
| **Vertex AI Agent Engine** | Managed runtime — runs the ADK pipeline as an HTTP-queryable service |
| **Cloud Scheduler** | Triggers the pipeline at 7 AM ET daily via HTTP POST |
| **Secret Manager** | Stores all credentials (OpenAI, Instagram, NewsAPI, football-data tokens) |
| **Cloud Storage** | `football-ig-post-images` bucket: hosts published JPEG images (public) and `dedup/seen.json` (persistent dedup state) |
| **Service Account** | `football-content-agent-sa` — has `aiplatform.user`, `secretmanager.secretAccessor`, `storage.objectAdmin`, `serviceusage.serviceUsageConsumer` |

### Environment Detection

The code detects Agent Engine via `AGENT_ENGINE=1` (injected as an env var at deploy time) and switches behaviour:

| Behaviour | Local Dev | Agent Engine |
|---|---|---|
| Credentials | `.env` file | Secret Manager |
| Output directory | `out/` | `/tmp/out/` |
| Dedup state | `data/seen.json` | `gs://football-ig-post-images/dedup/seen.json` |
| Vertex AI | Optional (env var) | Always on |

---

## Project Structure

```
footballContentAgent-IG/
├── app/
│   ├── agent.py                  # root_agent (SequentialAgent) definition
│   ├── config.py                 # Config singleton, Secret Manager access
│   ├── pipeline_app.py           # FootballPipelineApp — Agent Engine entrypoint
│   ├── models/                   # Pydantic models (RawIdea, PostPlan, FinalPost …)
│   ├── prompts/                  # Markdown prompt files per agent
│   ├── assets/                   # Badge images, fonts
│   ├── sub_agents/
│   │   ├── fetcher.py
│   │   ├── idea_judge.py
│   │   ├── idea_ranker.py
│   │   ├── content_generator.py
│   │   ├── researcher.py
│   │   ├── content_planner.py
│   │   ├── caption_writer.py
│   │   └── publisher.py
│   └── tools/
│       ├── dedup.py
│       ├── enricher.py
│       ├── compositor.py
│       ├── gcs.py
│       └── instagram.py
├── deploy.py                     # One-shot Agent Engine deployment script
├── deployment.md                 # Deployment guide + CI/CD outline
├── main.py                       # Local run entrypoint (adk run / python main.py)
├── requirements.txt
└── .env.example
```

---

## Running Locally

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt

# Copy and fill in credentials
cp .env.example .env

# Run the full pipeline
.venv/Scripts/python main.py

# Or with the ADK CLI
adk run app
```

## Deploying to Agent Engine

```bash
# Set secrets in Secret Manager first (see deployment.md)
.venv/Scripts/python deploy.py

# Save the printed resource name, then create the Cloud Scheduler job
# (see deployment.md for the full gcloud command)
```

See [deployment.md](deployment.md) for the complete deployment guide including Secret Manager setup, Cloud Scheduler configuration, and GitHub Actions CI/CD.

---

## Rate Limits to Know

| Source | Limit | Notes |
|---|---|---|
| football-data.org | 10 req/min (free) | Fetcher sleeps 7s between requests. One run ≈ 3 min. |
| NewsAPI | 100 req/day (Developer) | One request per run. Treat practical limit as ~5 runs/day. |
| Reddit | ~60 req/min | Public API, no daily cap. Occasional IP blocks. |
| RSS feeds | None | 6 public feeds, no auth. |
| gpt-image-2 | Tier-dependent | Each image takes 1–10 min including response body transfer. |
