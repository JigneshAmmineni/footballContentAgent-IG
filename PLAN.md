# Football Content Agent — ADK MVP Architecture Plan

## Context

Greenfield personal project at `footballContentAgent/` (UMass personal projects folder, `git init`'d, empty save for `contentagentresearch.md`). Goal: a daily email covering Big 5 Leagues (EPL, La Liga, Bundesliga, Serie A, Ligue 1) — match results, player updates (injuries/transfers/interviews), stat insights (running totals in MVP; era comparisons in V2). Designed to extend to Instagram carousel posts with image generation without a rewrite.

**Decisions confirmed by user:**
- Orchestration: **ADK via `agents-cli` from day 1** (not plain Python).
- Stats scope: **defer historical comparisons to V2** — MVP uses in-season running totals only.
- Approval: **draft file + manual send script** (`out/YYYY-MM-DD-draft.md` + `python -m src.send`).

**Environment already set up:**
- gcloud on `jigneshammineni@gmail.com`, project `gen-lang-client-0313493228` (AI Studio–backed), ADC fresh.
- `gws` CLI authenticated for Gmail send on the same account.
- `agents-cli` skills toolkit available; user wants prototype-first (no deployment yet).

**The ADK workflow enforces a specific order (Phases 0–7 in `google-agents-cli-workflow`):**
Understand → Study samples → Scaffold → Build → Evaluate → Deploy → Publish → Observe. This plan executes Phases 0–4; 5–7 are deferred.

Research doc (`contentagentresearch.md`) applied:
- **Boring wins** → linear `SequentialAgent` over a CrewAI-style crew.
- **Curation is where it succeeds or fails** → dedicated `curator_agent` with a rubric prompt, a different model family than the writer for the critic pass (avoids self-preference bias).
- **Plan-first (outline-then-fill)** → writer does outline → sections, not single-shot.
- **Config-as-files** → prompts in `prompts/*.md`, loaded by agents; swappable without touching code.
- **Scalability hook** → structured `ContentBundle` + `PlatformAdapter` ABC; newsletter and future Instagram publisher are siblings over a shared generation core.

## Reference Sample: `ambient-expense-agent`

Canonical ADK pattern for our use case per the skill ("scheduled, daily, email, ambient"). Structure we're borrowing (adapted for our scope):

- `expense_agent/agent.py` → our `content_agent/agent.py` (the `root_agent` definition)
- `expense_agent/config.py` → our `content_agent/config.py` (model name, feeds, recipient list)
- `expense_agent/fast_api_app.py` → **deferred** (only needed for Cloud Run / push triggers in Phase 3)
- `terraform/` → **deferred** (Phase 3)

**Not using** from the sample: Pub/Sub trigger (we run locally via `agents-cli run`), Workflow graph + HITL `RequestInput` (we use simpler `SequentialAgent`, file-based approval), Cloud Run deployment (prototype-first).

**Using** from the sample: the AI Studio/Vertex auto-detect in `config.py` (`GOOGLE_API_KEY` present → AI Studio; else → Vertex via ADC), function-tools pattern, log-based monitoring idea (for later).

## Recommended ADK Shape

```
root_agent = SequentialAgent(
    name="football_content_pipeline",
    sub_agents=[
        curator_agent,   # LlmAgent + tools: fetch_rss, fetch_football_data, fetch_reddit, dedup
        writer_agent,    # LlmAgent, reads curator's ContentBundle from state, outline-then-sections
        critic_agent,    # LlmAgent (different model family from writer), rewrites or approves
    ],
    after_agent_callback=write_draft_to_file,  # dumps final to out/YYYY-MM-DD-draft.md
)
```

- **Ingest is not an agent** — RSS / API / Reddit fetches are plain Python functions wrapped as tools. `curator_agent` calls them, receives raw candidates, then reasons over them to rank.
- **Dedup is a tool** called by `curator_agent` before ranking. Tool reads/writes `data/seen.json` (SHA-256 IDs). Swap for pgvector later without touching agent code.
- **Structured output**: curator emits a `ContentBundle` (JSON, validated via Pydantic) via ADK's `output_schema` feature. Writer consumes it. Critic receives both the bundle and the writer's draft.
- **Critic uses a different model family** than the writer — research's guidance to avoid self-preference bias. Writer: Gemini Pro; Critic: Gemini Flash (or flip; tune in AI Studio). If you want a *truly* different family, swap the critic to `gpt-4o-mini` via LiteLLM later.
- **State flow**: ADK passes state between sub-agents via `Context`. Keys: `candidates`, `bundle`, `draft`, `final`.

## Scalability Seams (day-one hooks for IG + image gen)

1. **`ContentBundle` Pydantic model** — structured, NOT a pre-formatted string. Lives in `content_agent/bundle.py`:
   ```python
   class ContentBundle(BaseModel):
       date: date
       match_results: list[MatchItem]
       player_updates: list[PlayerItem]
       stat_insights: list[StatItem]
       image_briefs: list[ImageBrief] = []   # populated in V2
   ```
2. **`PlatformAdapter` ABC** (`content_agent/publishers/base.py`): `format(bundle) -> str` + `publish(formatted) -> None`. Subclasses: `EmailPublisher` (MVP), `InstagramPublisher` (V2).
3. **Prompts as files** (`prompts/*.md`): `brand_voice.md`, `curator.md`, `writer.md`, `critic.md`, + later `image_brief.md`. Loaded by agents at startup via `config.py`.
4. **Dispatcher**: `publishers: list[PlatformAdapter]` configured in `config.py`. MVP = `[EmailPublisher]`. V2 = `[EmailPublisher, InstagramPublisher]`.
5. **Image generation hook**: `ImageBrief` carries prompt + aspect ratio. V2 adds `content_agent/tools/image.py` calling Imagen via `google-genai`.
6. **Deployment seam**: scaffolding as prototype now (`--deployment-target prototype` or equivalent). Later `agents-cli scaffold enhance . --deployment-target agent_runtime` (or `cloud_run` with a Cloud Scheduler → Pub/Sub push trigger) without rewriting agent code.

## AI Studio as Prompt Playground — concrete workflow

Each prompt iterates in AI Studio with *real* candidate data, then lands in `prompts/*.md`.

### Step 1 — dump real candidates locally
Create `scratch/dump_samples.py` (standalone Python, NOT an ADK tool): runs the same ingest/dedup logic your `curator_agent` will use, serializes ~30 candidates to `scratch/samples.json` (gitignored).

```python
# scratch/dump_samples.py — illustrative
from content_agent.tools.ingest import fetch_rss, fetch_football_data, fetch_reddit
from content_agent.tools.dedup import dedup
candidates = dedup(fetch_rss() + fetch_football_data() + fetch_reddit())
json.dump([c.model_dump() for c in candidates[:30]], open("scratch/samples.json", "w"), default=str)
```

Why not just call `curator_agent` with `--dry-run`? Because you want raw pre-LLM candidates to paste into AI Studio, not the curator's already-filtered output.

### Step 2 — iterate in aistudio.google.com
Open AI Studio → new chat → **Gemini 2.5 Pro** (or whichever the latest is; confirm via `uv run --with google-genai python -c "from google import genai; client = genai.Client(vertexai=True, location='global'); [print(m.name) for m in client.models.list()]"`).

Paste a prompt shaped like:

```
<system>
You are a soccer news curator for a daily Big 5 Leagues newsletter.
Rubric (each 1–25, sum = 100):
- MATCH IMPORTANCE: top-of-table, derbies, relegation
- PLAYER IMPACT: injuries to stars, transfers, standout performances
- STAT NOVELTY: records, unusual patterns, running totals
- FRESHNESS: not covered in the last 7 days
</system>

<candidates>
[paste 20–30 items from scratch/samples.json verbatim]
</candidates>

Output JSON matching this schema:
{"picks": [{"id": "...", "score": int, "category": "match|player|stat", "reason": "..."}]}
```

Toggle **Structured output** in the right panel — AI Studio enforces the schema. Tweak the rubric, role, output shape until picks match editorial intuition.

### Step 3 — export to ADK
Click **"Get code"** → Python → you get a `google-genai` snippet. You don't paste the snippet wholesale; you paste the *system prompt text* into `prompts/curator.md` and reuse the JSON schema as a Pydantic model for ADK's `output_schema`.

Repeat for `writer.md` (outline → sections), `critic.md` (rubric-based rewrite).

### Step 4 — smoke test in ADK
`agents-cli run "generate today's newsletter"` → sub-agents run in sequence → draft lands in `out/YYYY-MM-DD-draft.md`. If something looks off, go back to AI Studio with the same inputs and iterate the prompt.

**Tip**: AI Studio caps on very long pastes — if 30 candidates blows past the comfortable context, tune with `dump_samples.py --limit 10` and let the production run handle the full set.

## Target File Layout (post-scaffold)

`agents-cli scaffold create` generates most of this. Italics mark files we hand-write/customize.

```
footballContentAgent/
├── .env                          # GOOGLE_API_KEY (user-managed, never read by Claude)
├── .env.example                  # template
├── .gitignore
├── pyproject.toml                # scaffold-generated; we add: feedparser, requests, pydantic
├── README.md                     # scaffold-generated; we customize
├── contentagentresearch.md       # existing (unchanged)
├── DESIGN_SPEC.md                # ← we write: purpose, tools, constraints, success criteria
├── content_agent/
│   ├── __init__.py
│   ├── agent.py                  # ← SequentialAgent + 3 sub-agents
│   ├── config.py                 # ← model names, feed list, recipient, prompt loader
│   ├── bundle.py                 # ← Pydantic models: ContentBundle, MatchItem, PlayerItem, StatItem, ImageBrief
│   ├── sub_agents/
│   │   ├── curator.py            # ← LlmAgent + rubric + output_schema=ContentBundle
│   │   ├── writer.py             # ← LlmAgent reading bundle, outline-then-sections
│   │   └── critic.py             # ← LlmAgent (different model) with rewrite capability
│   ├── tools/
│   │   ├── ingest.py             # ← fetch_rss, fetch_football_data, fetch_reddit (ADK function tools)
│   │   ├── dedup.py              # ← sha256 + seen.json; signature stable for pgvector swap
│   │   └── send.py               # ← not a tool — standalone script using gws gmail send
│   ├── publishers/
│   │   ├── __init__.py
│   │   ├── base.py               # ← PlatformAdapter ABC
│   │   └── email.py              # ← EmailPublisher wrapping gws
│   └── callbacks.py              # ← after_agent_callback: write bundle+draft to out/
├── prompts/
│   ├── brand_voice.md            # ← tone, POV, what to avoid (personal voice)
│   ├── curator.md                # ← tuned in AI Studio, pasted here
│   ├── writer.md
│   └── critic.md
├── scratch/
│   └── dump_samples.py           # ← fetch candidates -> scratch/samples.json for AI Studio
├── data/
│   ├── seen.json                 # dedup memory (gitignored)
│   └── archive/                  # past bundles as JSON (for V2 novelty checks against memory)
├── out/                          # drafts awaiting approval: YYYY-MM-DD-draft.md (gitignored)
├── eval/
│   └── curator.evalset.json      # 2–3 cases: given candidates X, picks should include Y
└── tests/
    ├── test_dedup.py             # unit: SHA-256 idempotent, seen.json persists
    └── test_bundle.py            # unit: Pydantic validation roundtrip
```

## Model Routing (AI Studio models, hybrid per research)

- **Curator**: Gemini 2.5 Pro — strong judgment for ranking.
- **Writer**: Gemini 2.5 Pro — voice quality matters.
- **Critic**: Gemini 2.5 Flash — different tier breaks self-preference somewhat; cheaper. (If the critic keeps rubber-stamping the writer's output, swap to a different family via LiteLLM later — research's recommendation.)
- **Bulk summarization (future)**: Gemini 2.5 Flash-Lite for any batched item summarization.

Confirm exact latest model IDs via `uv run --with google-genai python -c "from google import genai; c = genai.Client(); [print(m.name) for m in c.models.list()]"` — don't hardcode from memory (model-preservation rule).

## Data Sources

- **RSS (free)**: BBC Sport, Guardian Football, ESPN FC, 90min, Football365, Goal.com. `feedparser` in `content_agent/tools/ingest.py::fetch_rss`.
- **Match results (free)**: football-data.org free tier covers all Big 5. Endpoint `/v4/matches?competitions=PL,PD,BL1,SA,FL1&dateFrom=<today-1>&dateTo=<today>`. 10 req/min. API key goes in `.env` as `FOOTBALL_DATA_TOKEN`, consumed by `fetch_football_data`.
- **Social/discussion (free)**: Reddit `r/soccer/new.json?limit=50` with browser User-Agent. Research confirms this works unauth. `fetch_reddit` consumes it.
- **Full bodies (free)**: Jina Reader (`https://r.jina.ai/<url>`) — zero config, pulls clean markdown. Called on-demand by writer when a headline warrants expansion (future; not MVP).
- **Stats for comparisons**: deferred to V2 via `worldfootballR` CSV dumps cached locally.

## Execution Phases

### Phase 0 — Understand (write `DESIGN_SPEC.md`)
Per the ADK workflow: the spec is the source of truth for the scaffold. I'll draft it from this plan (purpose, example inputs/outputs, tools with auth details, constraints/safety, success criteria, reference sample `ambient-expense-agent`). You approve it before we scaffold.

### Phase 1 — Study samples
Already done (`ambient-expense-agent` report above). Applying: `config.py` env-based provider auto-detect; function-tools for ingest/dedup; structured-output agents for curator; sub-agent composition.

### Phase 2 — Scaffold
Because the folder already has `contentagentresearch.md` and `.git/`, we handle one of:
- **Preferred**: `agents-cli scaffold create` inside the current folder (if the CLI supports scaffolding into a non-empty dir — we verify with `--help` / dry-run at execution time). The `--deployment-target prototype` flag skips Terraform/CI/CD generation.
- **Fallback**: scaffold into a sibling dir, move contents in, preserve `.git/`.

During scaffold prompts, select: Python, Gemini (AI Studio), prototype, no datastore, no A2A, no Memory Bank. These match the `DESIGN_SPEC.md` we write in Phase 0.

Immediately after scaffold: `agents-cli info` to confirm structure, `uv sync` to install deps.

### Phase 3 — Build
1. Add `FOOTBALL_DATA_TOKEN` to `.env.example` (NOT `.env` — user adds real token themselves per your global rule).
2. `content_agent/bundle.py`: Pydantic models.
3. `content_agent/tools/ingest.py`: three fetcher functions returning `list[Candidate]`.
4. `content_agent/tools/dedup.py`: SHA-256 hash + `data/seen.json` round-trip. Stable signature for future pgvector swap.
5. `content_agent/sub_agents/curator.py`: `LlmAgent` with `tools=[fetch_rss, fetch_football_data, fetch_reddit, dedup]`, `output_schema=ContentBundle`, instruction loaded from `prompts/curator.md`.
6. `content_agent/sub_agents/writer.py`: `LlmAgent` reading `ContentBundle` from state, two-stage (outline → sections), instruction from `prompts/writer.md`.
7. `content_agent/sub_agents/critic.py`: `LlmAgent` on different model tier, rewrite-or-approve, instruction from `prompts/critic.md`.
8. `content_agent/agent.py`: `root_agent = SequentialAgent(sub_agents=[...], after_agent_callback=write_draft_to_file)`.
9. `content_agent/callbacks.py`: `write_draft_to_file(context)` → `out/YYYY-MM-DD-draft.md` + JSON bundle snapshot in `data/archive/`.
10. `content_agent/publishers/{base,email}.py`: ABC + `EmailPublisher` wrapping `gws gmail` via subprocess.
11. `content_agent/tools/send.py`: standalone `__main__` script (invoked as `python -m content_agent.tools.send YYYY-MM-DD`) that reads the approved draft and ships it.
12. `scratch/dump_samples.py`: imports the ingest tools, dumps to JSON.
13. `prompts/*.md`: start with plausible first drafts; iterate via AI Studio (Step 2 above).

Smoke tests after each sub-agent lands: `agents-cli run "generate today's newsletter"`.

### Phase 4 — Evaluate
Per skill: MANDATORY, not optional. Start with 2–3 cases in `eval/curator.evalset.json`:
- Given a fixed set of 20 candidates (snapshot `samples.json`), curator's picks should include a specific match result and exclude a specific stale item.
- Given a `ContentBundle`, writer's output length is in range and each section references bundle items.
- Critic produces fewer than N rewrites on a known-good draft.

Run: `agents-cli eval run`. Iterate prompts until green. Add edge cases after core passes.

**No pytest on LLM content** (per skill's explicit warning). Pytest covers `dedup`, `bundle` Pydantic roundtrip, ingest parsers — code correctness only.

### Phase 5 — Deploy (**deferred**)
`agents-cli scaffold enhance . --deployment-target cloud_run` (with Cloud Scheduler → Pub/Sub) or `agent_runtime`. Not doing now.

### Phase 6 — Publish (**deferred**)
Gemini Enterprise registration. Not doing now.

### Phase 7 — Observe (**deferred**)
Cloud Trace + BigQuery Analytics. Not doing now.

## V2 Roadmap (Instagram + images)

Each item hooks into an existing seam — no core rewrites:
1. Populate `ImageBrief` in writer prompt (one brief per section).
2. `content_agent/tools/image.py` calls Imagen via `google-genai` (AI Studio path — same `GOOGLE_API_KEY`).
3. `content_agent/publishers/instagram.py`: `InstagramPublisher(PlatformAdapter)` formats bundle as a carousel (cover + 3–5 slides), calls image tool per slide, posts via Graph API (Basic Display deprecated; business account needed).
4. `config.publishers = [EmailPublisher, InstagramPublisher]`.
5. Novelty check: before writer runs, a callback reads `data/archive/*.json` from the last 7 days, cosine-compares bundle candidates, flags near-duplicates. pgvector when volume warrants.

## Files to Create (Phase 0–4)

After scaffold (which creates pyproject, README, initial `content_agent/`, tests skeleton, eval skeleton, .gitignore):

- Hand-written: `DESIGN_SPEC.md`
- `content_agent/config.py`, `content_agent/bundle.py`, `content_agent/agent.py`, `content_agent/callbacks.py`
- `content_agent/sub_agents/{curator,writer,critic}.py`
- `content_agent/tools/{ingest,dedup,send}.py`
- `content_agent/publishers/{__init__,base,email}.py`
- `prompts/{brand_voice,curator,writer,critic}.md`
- `scratch/dump_samples.py`
- `eval/curator.evalset.json`
- `tests/{test_dedup,test_bundle}.py`
- `.env.example` additions: `GOOGLE_API_KEY`, `GOOGLE_GENAI_USE_VERTEXAI=FALSE`, `FOOTBALL_DATA_TOKEN`

## Verification

- `agents-cli info` shows the scaffolded project correctly.
- `uv sync` installs cleanly; `agents-cli lint` passes.
- `uv run pytest` passes (code correctness only).
- `python scratch/dump_samples.py` → `scratch/samples.json` has ~30 real Big-5 candidates; you paste a subset into AI Studio and the curator prompt produces editorially-sound picks.
- `agents-cli run "generate today's newsletter"` → sub-agents run in sequence → `out/YYYY-MM-DD-draft.md` contains: title, match results section, player updates section, stat insights section. No duplicates across sections. Matches match today's real results.
- `agents-cli eval run` on the 2–3 seeded cases → all green.
- `python -m content_agent.tools.send YYYY-MM-DD --dry-run` → prints recipient, subject, body.
- `python -m content_agent.tools.send YYYY-MM-DD` → email arrives in inbox.
- **Scalability dry-run**: subclass `PlatformAdapter` with a no-op `StdoutPublisher`, wire it in `config.publishers`, confirm generation is format-agnostic (no email-specific fields leak into the `ContentBundle`).
