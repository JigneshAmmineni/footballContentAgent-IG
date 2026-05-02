"""Two-stage idea pipeline: judge (filter) -> ranker (order).

Intermediate files written for inspection:
  scratch/samples.json    -- fetcher output  (input to judge)
  scratch/candidates.json -- judge output    (input to ranker)
  scratch/approved.json   -- ranker output   (final top-15)

Usage:
    .venv/Scripts/python scratch/run_judge.py
    .venv/Scripts/python scratch/run_judge.py --dry-run   # skip writing seen.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from app.config import config
from app.models.raw_idea import RawIdea
from app.tools.dedup import dedup
from app.sub_agents.idea_judge import idea_judge_agent
from app.sub_agents.idea_ranker import idea_ranker_agent

SAMPLES    = Path(__file__).parent / "samples.json"
CANDIDATES = Path(__file__).parent / "candidates.json"
APPROVED   = Path(__file__).parent / "approved.json"
TOP_N = 10


def _run_agent(agent, app_name: str, payload_text: str) -> dict:
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)
    session = session_service.create_session_sync(app_name=app_name, user_id="local")
    message = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=payload_text)],
    )
    for _ in runner.run(user_id="local", session_id=session.id, new_message=message):
        pass
    final = session_service.get_session_sync(app_name=app_name, user_id="local", session_id=session.id)
    return final.state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't update seen.json (re-runnable on same data)")
    parser.add_argument("--ranker-only", action="store_true",
                        help="Skip judge stage; read candidates.json directly and re-run ranker")
    args = parser.parse_args()

    if args.ranker_only:
        if not CANDIDATES.exists():
            print(f"No candidates.json found at {CANDIDATES}. Run without --ranker-only first.")
            sys.exit(1)
        enriched = json.loads(CANDIDATES.read_text(encoding="utf-8"))
        print(f"Loaded {len(enriched)} candidates from {CANDIDATES}")
        _run_ranker(enriched)
        return

    if not SAMPLES.exists():
        print(f"No samples.json found at {SAMPLES}. Run dump_samples.py first.")
        sys.exit(1)

    raw = json.loads(SAMPLES.read_text(encoding="utf-8"))
    ideas = [RawIdea(**r) for r in raw]
    print(f"Loaded {len(ideas)} ideas from {SAMPLES}")

    if args.dry_run:
        fresh = ideas
        print(f"Dry-run: skipping seen.json, passing all {len(fresh)} ideas to judge")
    else:
        fresh = dedup(ideas, config.seen_file)
        print(f"After dedup: {len(fresh)} fresh ideas (skipped {len(ideas) - len(fresh)})")

    if not fresh:
        print("Nothing new -- exiting.")
        CANDIDATES.write_text("[]", encoding="utf-8")
        APPROVED.write_text("[]", encoding="utf-8")
        return

    # Build a lookup so we can enrich candidates with content_hint + fetched_at
    raw_lookup = {idea.id: idea for idea in fresh}

    # Stage 1: Judge (filter)
    print(f"\nStage 1 - idea_judge_agent ({len(fresh)} ideas -> up to 25 candidates)...")
    judge_payload = json.dumps(
        [i.model_dump(mode="json") for i in fresh],
        indent=2, default=str,
    )
    judge_state = _run_agent(idea_judge_agent, "idea_judge", f"Here are the raw ideas to judge:\n\n{judge_payload}")

    raw_candidates = judge_state.get("candidate_ideas", {})
    candidate_list = raw_candidates.get("ideas", []) if isinstance(raw_candidates, dict) else []

    # Enrich with content_hint + fetched_at from original RawIdea
    enriched = []
    for c in candidate_list:
        idea_id = c.get("raw_idea_id", "")
        orig = raw_lookup.get(idea_id)
        enriched.append({
            **c,
            "content_hint": orig.content_hint if orig else "",
            "fetched_at": orig.fetched_at.isoformat() if orig else None,
        })

    CANDIDATES.write_text(json.dumps(enriched, indent=2), encoding="utf-8")
    print(f"Stage 1 done: {len(enriched)} candidates -> {CANDIDATES}")

    if not enriched:
        print("No candidates approved -- exiting.")
        APPROVED.write_text("[]", encoding="utf-8")
        return

    _run_ranker(enriched)


def _run_ranker(enriched: list) -> None:
    print(f"\nStage 2 - idea_ranker_agent ({len(enriched)} candidates -> top {TOP_N})...")
    ranker_payload = json.dumps(enriched, indent=2, default=str)
    ranker_state = _run_agent(idea_ranker_agent, "idea_ranker", f"Here are the candidates to rank:\n\n{ranker_payload}")

    raw_approved = ranker_state.get("approved_ideas", {})
    approved_list = raw_approved.get("ideas", []) if isinstance(raw_approved, dict) else []

    approved_list = sorted(approved_list, key=lambda x: x.get("priority", 0), reverse=True)[:TOP_N]

    APPROVED.write_text(json.dumps(approved_list, indent=2), encoding="utf-8")
    print(f"Stage 2 done: {len(approved_list)} approved ideas -> {APPROVED}")


if __name__ == "__main__":
    main()
