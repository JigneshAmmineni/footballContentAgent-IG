"""Run idea judge on scratch/samples.json → scratch/approved.json.

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

SAMPLES = Path(__file__).parent / "samples.json"
APPROVED = Path(__file__).parent / "approved.json"
APP_NAME = "idea_judge"
USER_ID = "local"
TOP_N = 15


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't update seen.json (re-runnable on same data)",
    )
    args = parser.parse_args()

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
        print("Nothing new — exiting.")
        APPROVED.write_text("[]", encoding="utf-8")
        return

    session_service = InMemorySessionService()
    runner = Runner(
        agent=idea_judge_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )
    session = session_service.create_session_sync(app_name=APP_NAME, user_id=USER_ID)

    payload = json.dumps(
        [i.model_dump(mode="json") for i in fresh],
        indent=2,
        default=str,
    )
    message = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=f"Here are the raw ideas to judge:\n\n{payload}")],
    )

    print("Running idea_judge_agent…")
    for event in runner.run(
        user_id=USER_ID, session_id=session.id, new_message=message
    ):
        pass

    final = session_service.get_session_sync(
        app_name=APP_NAME, user_id=USER_ID, session_id=session.id
    )
    approved = final.state.get("approved_ideas", {})
    ideas_out = approved.get("ideas", []) if isinstance(approved, dict) else []

    # Hard cap: top TOP_N by priority
    ideas_out = sorted(ideas_out, key=lambda x: x.get("priority", 0), reverse=True)[:TOP_N]

    APPROVED.write_text(json.dumps(ideas_out, indent=2), encoding="utf-8")
    print(f"Approved {len(ideas_out)} ideas -> {APPROVED}")


if __name__ == "__main__":
    main()
