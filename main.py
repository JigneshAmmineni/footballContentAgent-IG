"""Local entry point for the football content pipeline.

Runs the same root_agent that gets deployed to Vertex AI Agent Engine, but
in-process via ADK's local Runner. Use this for development, debugging, and
once the pipeline is deployed, also as the script Cloud Scheduler triggers
(via Cloud Run Job) if we end up using Cloud Run instead of Agent Engine.

Usage:
    .venv/Scripts/python main.py
    .venv/Scripts/python main.py --stop-after-rank   # skip expensive image gen
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Force UTF-8 stdout so player names with accents (Atlético, Mbappé, etc.) print
# cleanly on Windows consoles.
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

_APP_NAME = "football_content_pipeline"
_USER_ID = "local"
_KICKOFF_MESSAGE = "Run the daily content pipeline."


def _build_agent(stop_after_rank: bool):
    # Lazy imports: each sub-agent is a module-level singleton, and importing
    # `app.agent.root_agent` parents them to the production SequentialAgent.
    # If we then try to re-parent the same singletons into a test pipeline, the
    # ADK Pydantic validator rejects it. So pick exactly one path.
    if not stop_after_rank:
        from app.agent import root_agent
        return root_agent

    from google.adk.agents import SequentialAgent
    from app.sub_agents.fetcher import fetcher_agent
    from app.sub_agents.idea_judge import idea_judge_agent
    from app.sub_agents.idea_ranker import idea_ranker_agent
    return SequentialAgent(
        name="football_content_pipeline_test",
        description="Test pipeline: fetch + judge + rank only.",
        sub_agents=[fetcher_agent, idea_judge_agent, idea_ranker_agent],
    )


async def _run(stop_after_rank: bool) -> None:
    agent = _build_agent(stop_after_rank)
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=_APP_NAME, session_service=session_service)
    session = await session_service.create_session(app_name=_APP_NAME, user_id=_USER_ID)
    message = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=_KICKOFF_MESSAGE)],
    )

    async for _event in runner.run_async(
        user_id=_USER_ID,
        session_id=session.id,
        new_message=message,
    ):
        # Events are auto-traced + state-mutated by the runner; we don't need to
        # inspect them here. Logger output from the sub-agents covers progress.
        pass

    final = await session_service.get_session(
        app_name=_APP_NAME, user_id=_USER_ID, session_id=session.id
    )
    final_posts = final.state.get("final_posts") or []
    published = final.state.get("published_posts") or []
    approved = (final.state.get("approved_ideas") or {}).get("ideas") or []
    print(f"\nDone. {len(approved)} approved · {len(final_posts)} generated · {len(published)} published.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stop-after-rank",
        action="store_true",
        help="Skip the content generator (no image gen, no captions). Cheap test mode.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet noisy upstream loggers.
    logging.getLogger("google_adk").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    asyncio.run(_run(args.stop_after_rank))


if __name__ == "__main__":
    main()
