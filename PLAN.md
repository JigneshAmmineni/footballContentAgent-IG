# Football Content Agent — Plan

---

## Section 1: Content Strategy, Data Sources & Candidate Pipeline

### Content Categories

Content falls into three broad buckets. These are not mutually exclusive and are not an enum — a single raw idea can span categories. The idea judge assigns a free-form `content_direction`, not a fixed type.

**News/reactive** (event-driven):
- Important match results (title race, relegation battles, popular scorers)
- Injury news
- Transfer news and rumors
- Notable press conference quotes

**Structured/scheduled** (fixture- and data-driven):
- Match preview cards
- Form guide posts (last 5 results for teams in meaningful positions)
- Player milestone posts (e.g. "Endrik just scored his 10th league goal at 18")

**Derived/editorial** (aggregated, no single source):
- Stat comparisons
- Debate/engagement prompts

---

### Data Sources

All sources are free. Rate limit mitigations are baked into the fetcher implementations.

| Source | Covers | Auth | Rate limit | Mitigation |
|---|---|---|---|---|
| **football-data.org** | Fixtures, results, standings, scorers — all Big 5 | `FOOTBALL_DATA_TOKEN` in `.env` | 10 req/min | 7s sleep between calls; ~15 reqs/day total |
| **NewsAPI.org** | Aggregated football news from 150+ publishers | `NEWS_API_KEY` in `.env` | 100 req/day | Max 5 broad queries per run; no pagination |
| **Reddit r/soccer** | Viral news, transfer rumors, quotes, community reactions | None (unauthenticated JSON) | ~60 req/min | Browser `User-Agent` header; 3 requests (new, hot, rising) |
| **FBref** (via `soccerdata`) | Deep player/team stats, cumulative numbers | None (scraping) | Soft — scraping protection | soccerdata's built-in 5s delay + local file cache |
| **Understat** (via `soccerdata`) | xG, shot maps, match stats | None (scraping) | Soft — scraping protection | Same as FBref |
| **BBC Sport RSS** | Match reports, injuries, transfers | None | None | — |
| **Sky Sports RSS** | Transfers, injuries, manager quotes | None | None | — |
| **Guardian Football RSS** | Match analysis, news | None | None | — |
| **ESPN FC RSS** | Results, news | None | None | — |
| **90min RSS** | News, rumors | None | None | — |
| **Goal.com RSS** | News, transfer rumours | None | None | — |

See `DATA_SOURCES.md` for API registration links, env var names, and endpoint details.

All fetchers run **once per day** as a single batch job.

---

### Candidate Queue Structure

Each fetcher produces `RawIdea` objects that enter a shared queue. Dedup runs across all sources before the queue is handed to the judge.

```
RawIdea:
  id: str                   # SHA-256 of (source + content_fingerprint)
  source: str               # "football_data" | "newsapi" | "reddit" | "fbref" | "understat" | "rss:{outlet}"
  content_hint: str         # short natural-language summary of the event/data point
  raw_data: dict            # original payload from source
  fetched_at: datetime
  suggested_type: str | None  # fetcher's non-binding hint ("milestone", "preview", "news", etc.)
```

Dedup is SHA-256 keyed on `(source, content_fingerprint)`. A separate semantic near-duplicate pass (string similarity) collapses cross-source duplicates about the same event before the judge sees the queue.

---

### Idea Judge

An LLM call sitting at the end of the deduplicated queue. Processes each `RawIdea` and either rejects it or emits an `ApprovedIdea`.

**Judge guidelines (rubric):**

1. **"Do people care about this right now?"** — primary filter. Reason about current cultural relevance and momentum, not club size or player fame. An up-and-coming player generating buzz clears this bar; a routine result from a mid-table club does not.

2. **Cross-source corroboration signal** — if 2+ independent sources mention the same event or player, treat it as organic evidence of relevance. Single-source mentions require stronger reasoning to pass.

3. **Recency gate (news only)** — news ideas older than 48 hours are rejected. Stats, milestones, and comparisons are not time-gated.

4. **Compelling angle required** — the judge must articulate a specific `content_direction` for the post. If it cannot find a genuinely interesting angle, it rejects the idea.

5. **Daily subject cap** — reject any idea about a club or player already represented by 2 approved ideas in today's queue. Prevents single-subject flooding.

**ApprovedIdea output:**

```
ApprovedIdea:
  raw_idea_id: str
  priority: int             # 1–10; used downstream to order content generation
  content_direction: str    # free-form editorial brief (e.g. "Endrik debut — compare youth
                            #   numbers to historical peers at same age in Ligue 1")
  data_needed: list[str]    # additional fetches the content generator will need
```

The judge does **not** enforce a fixed post-type enum. `content_direction` is intentionally open-ended — content types overlap in practice and the list will grow over time.

---

## Section 2: Content Generation Pipeline & ADK Architecture

### ADK Agent Orchestration

The pipeline is a top-level `SequentialAgent` containing five named `LlmAgent`s. State flows through ADK session state between agents. Prompts live in `prompts/*.md`, loaded at startup by `config.py`. Deployment target is **Gemini Enterprise Agent Runtime** via `agents-cli deploy agent_runtime`.

```
root_agent = SequentialAgent("football_content_pipeline")
    │
    ├── NewsIngestAgent        # fetches all sources, deduplicates, writes raw_ideas to state
    ├── IdeaJudgeAgent         # reads raw_ideas, emits approved_ideas (output_schema=ApprovedIdeaList)
    ├── ImageGeneratorAgent    # per approved idea: routes → fetches/generates image → writes image paths to state
    ├── CaptionWriterAgent     # reads approved_ideas + image paths, writes draft_captions to state
    └── CaptionCriticAgent     # reads approved_ideas + draft_captions only (fresh context), writes final_posts
          │
          └── after_agent_callback: write_output_files → out/YYYY-MM-DD/{idea_id}/image.png + caption.txt
```

**State keys:**
```
raw_ideas:       list[RawIdea]          written by NewsIngestAgent
approved_ideas:  list[ApprovedIdea]     written by IdeaJudgeAgent
image_paths:     dict[idea_id, str]     written by ImageGeneratorAgent
draft_captions:  dict[idea_id, str]     written by CaptionWriterAgent
final_posts:     list[FinalPost]        written by CaptionCriticAgent
```

**Agent responsibilities:**

- **NewsIngestAgent** — `LlmAgent` with 8 fetcher tools (one per source). Calls tools, aggregates results, runs SHA-256 dedup + semantic near-duplicate collapse, writes `raw_ideas` to state. Prompt: `prompts/news_ingest.md`.

- **IdeaJudgeAgent** — `LlmAgent` with `output_schema=ApprovedIdeaList`. Reads `raw_ideas`, applies the judge rubric (Section 1), emits approved ideas sorted by priority. Prompt: `prompts/idea_judge.md`.

- **ImageGeneratorAgent** — `LlmAgent` with image generation tools (see Image Generation Module below). Iterates over `approved_ideas`, generates one image per idea, writes paths to `image_paths`. Prompt: `prompts/image_generator.md`.

- **CaptionWriterAgent** — `LlmAgent`. Reads `approved_ideas` + `image_paths`. For each idea, writes a hype/energetic caption driving engagement. Prompt: `prompts/caption_writer.md`.

- **CaptionCriticAgent** — `LlmAgent`. Receives only `approved_ideas` + `draft_captions` in context (not the writer's system prompt or chain of thought — enforcing the "fresh session" constraint via scoped state injection). Improves each caption and appends hashtags. Prompt: `prompts/caption_critic.md`.

**Prompts folder:**
```
prompts/
  brand_voice.md       # tone, POV, what to avoid — shared across writer and critic
  news_ingest.md       # ingest agent instructions
  idea_judge.md        # judge rubric prompt
  image_generator.md   # visual direction prompt (how to pick Imagen prompts per content type)
  caption_writer.md    # hype tone, engagement-driving, references brand_voice.md
  caption_critic.md    # review rubric: punchy, no fluff, hashtag generation
```

**Deployment note:** `deployment_metadata.json` already exists at project root (generated by `agents-cli scaffold`). Agent Runtime deployment: `agents-cli deploy agent_runtime`. Daily scheduling is configured via Cloud Scheduler after deployment (Phase 5 — deferred).

---

### ─── IMAGE GENERATION MODULE ───────────────────────────────────────────────
> This section is deliberately isolated. The image generation approach can be swapped
> without touching any other part of the pipeline. ImageGeneratorAgent uses these tools;
> the rest of the pipeline only cares about the image path that comes out.

**Three-path router** — Python function inside `ImageGeneratorAgent`'s tool set. Reads `content_direction` and routes to the appropriate generator. Not an LLM call.

```
content_direction keywords → generator path

contains "quote" | "said" | "press conference"    → Pillow quote card template
contains "scored" | "milestone" | "goal" | "hat"  → Pillow milestone card template
contains "vs" | "preview" | "fixture" | "kickoff" → Pillow match card template
contains "result" | "won" | "drew" | "lost"        → Pillow match card template
contains "form" | "last 5" | "run of"              → Pillow form guide (programmatic)
contains "stat" | "xG" | "radar" | "compared to"  → Mplsoccer chart
fallback                                            → Gemini Imagen
```

**Path A — Pillow Templates** (quote card, milestone card, match card, form guide)

Template spec (to be designed in Canva/Figma and exported as PNG with transparent zones):
- Canvas: 1080×1080px (Instagram square)
- Zone 1: full-bleed background image (player photo or team graphic)
- Zone 2: dark gradient overlay (bottom 40% of canvas, for text legibility)
- Zone 3: main text — centered, max 3 lines, 72px bold white
- Zone 4: source/badge strip — bottom bar, 32px, 60% opacity white
- Zone 5: account branding — top-right corner logo placeholder

Player/background photo sourcing (for quote card and milestone card):
1. **Jina Reader first** — if the `RawIdea` has a `source_url`, call `https://r.jina.ai/{source_url}` and extract `og:image` from the returned markdown. Download and use as Zone 1 background.
2. **Gemini Imagen fallback** — if Jina Reader returns no image or the URL has no source article, generate via Imagen 3 with a context-aware prompt (see below).

Team badge sourcing (for match cards):
- football-data.org returns a `crest` URL per team in every fixtures/standings response.
- Cache badges locally to `data/badges/{team_id}.png` on first fetch. Reuse on subsequent runs.

**Path B — Mplsoccer + Pillow composite** (stat comparisons, form guide)

All chart posts go through a two-step process:
1. `render_chart_figure(data, chart_type)` — Mplsoccer/Matplotlib renders the chart as an in-memory figure (radar, bar, W/D/L strip). Output: raw figure, not a file.
2. `composite(background, content_zone, overlays)` — Pillow places the figure into the content zone of a styled background (team color gradient or stadium photo via Jina Reader), adds title text and badges.

The compositing step is **shared across all three Pillow paths** — quote cards, stat cards, and match cards all go through `composite()`. The only difference is what's in the content zone: a text block, a chart figure, or a scoreline layout.

**Path C — Gemini Imagen 3** (non-standard content and player photo fallback)

Called via `google-genai` SDK using the same `GOOGLE_API_KEY`.

The Imagen prompt is **generated contextually** — not a fixed template. The `image_generator.md` prompt instructs the agent to derive a visual direction from `content_direction`:

```
"goal scored / hat-trick / milestone"      → dramatic mid-kick shooting action, motion blur, stadium crowd
"transfer / signing / new club"            → player in celebratory pose, training ground setting
"injury news"                              → player on the sidelines, medical staff, contemplative
"press conference / manager quote"         → speaker at podium or microphone, press backdrop
"match preview"                            → two sets of fans in stadium, rivalry atmosphere, floodlights
"stat comparison"                          → abstract data visualization aesthetic, football field top-down
default                                    → dramatic stadium atmosphere, crowd, floodlights
```

Aspect ratio: `1:1` (1080×1080). Model: `imagen-3.0-generate-002` (or latest available — confirm at runtime).

### ─────────────────────────────────────────────────────────────────────────────

---

### Caption Pipeline

**CaptionWriterAgent prompt direction** (`prompts/caption_writer.md`):
- Tone: high-energy, hype, football fan voice — like a passionate supporter texting their mate
- Every caption must open with a hook (a fact, a question, or a bold statement — never "Here's")
- Drive engagement: end with a question or a call to action ("Drop your prediction below 👇", "Who does this better?")
- Length: 3–5 lines. No padding. Every line earns its place.
- Reference the `content_direction` brief; don't generalize

**CaptionCriticAgent prompt direction** (`prompts/caption_critic.md`):
- Fresh context: receives only the original `content_direction` brief + the draft caption
- Review rubric: Is the hook punchy? Does every line add something? Does it end with engagement?
- Cut anything that sounds like a press release or a match report
- Append 5–8 hashtags: 2 competition-specific (#PremierLeague), 2 player/club-specific, 2 generic football (#football #UCL style), 1 branded placeholder (#YourAccountName)
- Output: revised caption + hashtags as a single block, ready to post

**FinalPost output:**
```
FinalPost:
  idea_id: str
  image_path: str       # out/YYYY-MM-DD/{idea_id}/image.png
  caption: str          # revised caption + hashtags
  priority: int         # carried from ApprovedIdea for ordering
```

---

## Section 3: File Layout & Build Sequence

### File Layout

The ADK package root is `app/` — this is fixed by the existing scaffold and Agent Runtime deployment. Do not rename it.

**Deviations from original design:**
- `prompts/` lives at `app/prompts/` (not project root) — Agent Runtime bundles `app/` wholesale; prompts must be inside it to survive deployment.
- `assets/templates/` lives at `app/assets/templates/` — same reason.
- `NewsIngestAgent` is a `BaseAgent` subclass (pure Python), not an `LlmAgent` — fetching all sources and deduplicating is fully deterministic; there is no reasoning task requiring an LLM here. State is written directly via `ctx.session.state`.
- Agent instructions use ADK's `{state_key}` template substitution to inject upstream state (e.g. `{raw_ideas}`) rather than passing data through a `before_agent_callback`.

All agent code lives inside `app/`. Data, output, scratch, and eval remain at the project root (local dev only; GCS replaces them in production).

```
footballContentAgent/
│
├── app/                              # ADK package root — Agent Runtime bundles this directory
│   ├── __init__.py
│   ├── agent.py                      # root_agent = SequentialAgent(...) — ADK entrypoint
│   ├── config.py                     # Config dataclass: model names, feed URLs, prompt loader
│   ├── callbacks.py                  # write_output_files() after_agent_callback
│   │
│   ├── app_utils/
│   │   └── .requirements.txt         # pinned deps for Agent Runtime — add new deps here
│   │
│   ├── models/                       # Pydantic data contracts — shared by all agents
│   │   ├── __init__.py
│   │   ├── raw_idea.py               # RawIdea
│   │   ├── approved_idea.py          # ApprovedIdea, ApprovedIdeaList (output_schema)
│   │   └── final_post.py             # FinalPost
│   │
│   ├── sub_agents/
│   │   ├── __init__.py
│   │   ├── news_ingest.py            # NewsIngestAgent
│   │   ├── idea_judge.py             # IdeaJudgeAgent
│   │   ├── image_generator.py        # ImageGeneratorAgent
│   │   ├── caption_writer.py         # CaptionWriterAgent
│   │   └── caption_critic.py         # CaptionCriticAgent
│   │
│   └── tools/
│       ├── __init__.py
│       ├── dedup.py                  # sha256_id() + semantic_dedup() — stable interface
│       │
│       ├── fetchers/                 # one file per source; all subclass BaseFetcher
│       │   ├── __init__.py
│       │   ├── base.py               # BaseFetcher ABC: fetch() -> list[RawIdea]
│       │   ├── football_data.py      # FootballDataFetcher
│       │   ├── newsapi.py            # NewsApiFetcher
│       │   ├── reddit.py             # RedditFetcher
│       │   ├── rss.py                # RssFetcher (all 6 outlets, configured via config.py)
│       │   ├── fbref.py              # FbrefFetcher
│       │   └── understat.py          # UnderstatFetcher
│       │
│       └── image/                    # ── IMAGE GENERATION MODULE (isolated) ──
│           ├── __init__.py
│           ├── router.py             # route(content_direction) -> GeneratorPath enum
│           ├── sourcing.py           # get_background_image(): Jina Reader → Imagen fallback
│           ├── composite.py          # composite(background, content_zone, overlays) -> PIL.Image
│           ├── pillow_renderer.py    # render_text_zone(), render_badges(), render_form_dots()
│           ├── chart_renderer.py     # render_chart_figure(data, chart_type) -> matplotlib Figure
│           └── imagen_client.py      # generate_imagen(prompt, aspect) -> PIL.Image
│
├── prompts/                          # prompt files — edit without touching code
│   ├── brand_voice.md
│   ├── news_ingest.md
│   ├── idea_judge.md
│   ├── image_generator.md
│   ├── caption_writer.md
│   └── caption_critic.md
│
├── assets/
│   └── templates/                    # base Pillow template PNGs (placeholder until designed)
│       ├── quote_card.png
│       ├── match_card.png
│       └── stat_card.png
│
├── data/
│   ├── seen.json                     # dedup memory (gitignored)
│   ├── badges/                       # cached team badge PNGs from football-data.org
│   └── archive/                      # past FinalPost JSON snapshots
│
├── out/                              # daily output: out/YYYY-MM-DD/{idea_id}/ (gitignored)
│   └── YYYY-MM-DD/
│       └── {idea_id}/
│           ├── image.png
│           └── caption.txt
│
├── scratch/
│   └── dump_samples.py               # standalone: fetch → dump raw_ideas to scratch/samples.json
│
├── eval/
│   └── judge.evalset.json            # 2–3 fixed-input eval cases for IdeaJudgeAgent
│
├── tests/
│   └── unit/
│       ├── test_models.py            # Pydantic roundtrip validation
│       ├── test_dedup.py             # sha256 idempotence, seen.json persistence
│       └── test_fetchers.py          # fetcher contract tests (mock HTTP)
│
├── DATA_SOURCES.md
├── PLAN.md
├── deployment_metadata.json          # existing — points to Agent Runtime instance
└── .env.example
```

**New deps to add to `app/app_utils/.requirements.txt`:**
- `soccerdata` — FBref + Understat wrappers
- `mplsoccer` — radar charts and football-specific visualizations
- `Pillow` — image compositing
- `matplotlib` is already present via numpy/scipy transitive deps — confirm at build time

---

### OOP Design Principles

**`BaseFetcher` ABC** — all fetchers implement one interface: `fetch() -> list[RawIdea]`. Adding a new source means subclassing `BaseFetcher`, not touching any agent or config. `NewsIngestAgent` receives `list[BaseFetcher]` from `Config`, calls `fetch()` on each.

**`Config` dataclass** — single source of truth. Instantiated once, injected into agents and tools. Fields: `model_names: dict`, `fetchers: list[BaseFetcher]`, `prompt_dir: Path`, `output_dir: Path`, `data_dir: Path`. No global state, no scattered constants.

**`composite()` as shared core** — all image paths produce a `PIL.Image` and call the same `composite(background, content_zone, overlays)` function. The image generation module boundary is `get_or_generate_image(idea: ApprovedIdea) -> Path` — one function in, one file path out.

**Pydantic models as inter-agent contracts** — `RawIdea`, `ApprovedIdea`, `FinalPost` are the only shared types. Agents communicate via ADK session state using these types serialized to JSON. Changing an agent's internal logic never requires changing another agent's code.

---

### Build Sequence

Build bottom-up. Each layer is independently testable before the next begins.

| Step | What | Verify |
|---|---|---|
| 1 | Add missing deps to `.requirements.txt` | `python -c "import soccerdata, mplsoccer, PIL"` |
| 2 | `app/models/` — Pydantic models | `pytest tests/unit/test_models.py` |
| 3 | `app/config.py` — Config dataclass + prompt loader | instantiate Config, assert prompt files load |
| 4 | `app/tools/fetchers/base.py` + one fetcher (football_data.py first) | `python scratch/dump_samples.py --source football_data` |
| 5 | Remaining 5 fetchers | extend dump_samples.py to test each source |
| 6 | `app/tools/dedup.py` | `pytest tests/unit/test_dedup.py` |
| 7 | `app/tools/image/` — full image module | standalone script: given a test idea, produce image.png |
| 8 | `app/callbacks.py` | unit test: assert out/ directory structure created correctly |
| 9 | `app/sub_agents/news_ingest.py` + prompt | `agents-cli run "run news ingest only"`, inspect state |
| 10 | `app/sub_agents/idea_judge.py` + prompt | feed fixed raw_ideas from samples.json, inspect approved_ideas |
| 11 | `app/sub_agents/image_generator.py` + prompt | feed fixed approved_ideas, inspect image output |
| 12 | `app/sub_agents/caption_writer.py` + prompt | feed fixed approved_ideas + image paths, inspect draft captions |
| 13 | `app/sub_agents/caption_critic.py` + prompt | feed fixed approved_ideas + draft captions, inspect final captions |
| 14 | `app/agent.py` — wire root_agent | `agents-cli run "run full pipeline"` → out/ populated |
| 15 | `eval/judge.evalset.json` — 2–3 cases | `agents-cli eval run` → all green |
| 16 | Re-deploy to Agent Runtime | `agents-cli deploy agent_runtime` |

Prompts (`prompts/*.md`) are iterated in AI Studio between steps 9–13 — each agent gets a working first-draft prompt before its step, then refined against real data from `scratch/samples.json`.

---

## Roadmap

Improvements deferred from MVP. None of these require changes to the core pipeline — each hooks into an existing seam.

### Dynamic Compositing (Visual Variety)

**Problem:** Using the same Pillow template for every post causes the feed to look repetitive over time.

**Option A — Multiple template variants + LLM selection**
Design 3–5 layout variants per post type (different color schemes, text placement, crop styles). `ImageGeneratorAgent` picks a variant based on `content_direction`. Lightweight, bounded by how many templates you design.

**Option B — HTML/CSS → Playwright rendering**
`ImageGeneratorAgent` generates a post layout as HTML/CSS. Playwright renders it headlessly to a 1080×1080 PNG. Fully dynamic — no fixed templates. This is the approach used by Vercel's og-image and similar services. Requires a Playwright dependency and an LLM that reliably writes consistent HTML. Highest flexibility ceiling.

Implement Option A first (low friction), migrate to Option B when feed variety becomes a real constraint.

### Instagram Publishing
Wire up the Instagram Graph API once the content pipeline is proven locally. Requires a Facebook Business account and an approved app with `instagram_basic` + `instagram_content_publish` permissions. Media upload is URL-based (not direct file). Add `InstagramPublisherAgent` as a final step in the pipeline after `CaptionCriticAgent`. Deferred until content quality is validated manually.

### Historical Content Type
"This day X years ago" posts. Requires a verified event database (hand-curated JSON of 50–100 entries minimum) before this content type is enabled. Do not use model recall for historical claims — hallucination risk is too high. Deferred until the database exists.

### Source Citation & Fact Verification
Add `source_url` as a mandatory field on `ApprovedIdea`. `CaptionCriticAgent` rejects any idea not backed by a cited, retrievable source. Modular addition to the judge rubric — add when hallucination becomes a visible problem in production output.

### Posting Scheduler & Content Calendar
Cloud Scheduler triggers the daily pipeline after Agent Runtime deployment. Add a content calendar view (simple JSON or Google Sheet) so approved posts can be reviewed and reordered before publishing. Deferred to Phase 5.
