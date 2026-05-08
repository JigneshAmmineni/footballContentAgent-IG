"""Queryable wrapper for Agent Engine deployment.

AdkApp is designed for conversational agents and only exposes session
management methods — it has no query() entrypoint. Our pipeline is one-shot
(not conversational), so we use this lightweight wrapper instead.

Agent Engine calls query() when it receives an HTTP POST to the :query
endpoint (e.g. from Cloud Scheduler). query() mirrors main.py exactly.
"""
import asyncio
import concurrent.futures
import logging

_APP_NAME = "football_content_pipeline"
_USER_ID = "scheduler"


async def _run_pipeline() -> dict:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as genai_types
    from app.agent import root_agent

    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent,
        app_name=_APP_NAME,
        session_service=session_service,
    )
    session = await session_service.create_session(
        app_name=_APP_NAME, user_id=_USER_ID
    )
    message = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text="Run the daily content pipeline.")],
    )
    async for _ in runner.run_async(
        user_id=_USER_ID,
        session_id=session.id,
        new_message=message,
    ):
        pass
    final = await session_service.get_session(
        app_name=_APP_NAME, user_id=_USER_ID, session_id=session.id
    )
    final_posts = final.state.get("final_posts") or []
    published = final.state.get("published_posts") or []
    approved = (final.state.get("approved_ideas") or {}).get("ideas") or []
    return {
        "status": "completed",
        "approved": len(approved),
        "generated": len(final_posts),
        "published": len(published),
    }


class FootballPipelineApp:
    def query(self, **kwargs) -> dict:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
        # Agent Engine's FastAPI server already runs an asyncio event loop,
        # so asyncio.run() would fail with "cannot be called from a running
        # event loop". Running in a fresh thread gives us a clean event loop.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _run_pipeline())
            result = future.result()
        logging.getLogger(__name__).info(
            "Pipeline complete: %(approved)s approved · %(generated)s generated · %(published)s published",
            result,
        )
        return result
