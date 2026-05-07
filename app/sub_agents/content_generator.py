"""ContentGeneratorAgent — for each approved idea, runs the per-idea pipeline:

    enrich  →  (researcher fallback if article too short)  →
    content_planner LLM (with retry)  →  gpt-image-2  →  PIL compositor  →
    caption_writer LLM

Reads state["approved_ideas"] (written by idea_ranker_agent).
Writes state["final_posts"]: list[dict] of FinalPost.

Per-idea try/except boundary — one bad idea does not abort the run.
The content_planner LLM is retried up to 3 times on validation errors,
since structured-output JSON sometimes fails on a single malformed key.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
from datetime import date
from typing import Any, AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from openai import OpenAI
from PIL import Image

from app.config import config
from app.models import ApprovedIdea, EnrichedPost, FinalPost, PostPlan
from app.sub_agents.caption_writer import caption_writer_agent
from app.sub_agents.content_planner import content_planner_agent
from app.sub_agents.researcher import researcher_agent
from app.tools.compositor import composite
from app.tools.enricher import enrich

logger = logging.getLogger(__name__)

# If Jina Reader returns less than this many chars, we treat the fetch as thin
# and run the researcher agent to gather facts via web search.
# 300 chars is enough to confirm a result exists but not enough to name goalscorers.
_ARTICLE_TEXT_MIN_LENGTH = 800

# Stochastic JSON validation failures from gemini-2.5-pro hit the planner most;
# retry up to this many times before giving up on an idea.
_PLANNER_MAX_ATTEMPTS = 3
_PLANNER_RETRY_SLEEP_S = 5

# Pace down inter-idea LLM/image-gen calls to keep us under provider rate limits.
# Researcher now runs per-idea (3-4 Google searches) — extra buffer needed.
_INTER_IDEA_SLEEP_S = 15

# OpenAI image-gen timeout — gpt-image-2 high quality at 1024x1536 routinely takes 2-3 min.
_IMAGE_GEN_TIMEOUT_S = 240
_IMAGE_GEN_MAX_ATTEMPTS = 2
_IMAGE_GEN_RETRY_SLEEP_S = 15


class ContentGeneratorAgent(BaseAgent):
    """Iterates approved ideas, generating an image + caption for each."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        approved_raw = ctx.session.state.get("approved_ideas") or {}
        # idea_ranker writes ApprovedIdeaList; canonical shape is {"ideas": [...]}.
        approved_list = approved_raw.get("ideas") if isinstance(approved_raw, dict) else approved_raw
        if not approved_list:
            logger.warning("no approved ideas in state; nothing to generate")
            yield self._state_event(ctx, {"final_posts": []})
            return

        ideas = [ApprovedIdea(**i) for i in approved_list]
        final_posts: list[dict] = []

        for index, idea in enumerate(ideas):
            if index > 0:
                await asyncio.sleep(_INTER_IDEA_SLEEP_S)

            logger.info(
                "[%d/%d] priority=%d %s",
                index + 1, len(ideas), idea.priority, idea.content_direction[:80],
            )
            try:
                async for event in self._process_idea(ctx, idea, final_posts):
                    yield event
            except Exception as e:
                # Per-idea isolation: one bad idea must not kill the rest.
                logger.exception("idea %s failed: %s", idea.raw_idea_id, e)

        # Persist a manifest of every successful post for downstream poster/audit.
        yield self._state_event(ctx, {"final_posts": final_posts})
        self._write_manifest(final_posts)

    # ------------------------------------------------------------------ #
    # Per-idea pipeline
    # ------------------------------------------------------------------ #
    async def _process_idea(
        self,
        ctx: InvocationContext,
        idea: ApprovedIdea,
        final_posts: list[dict],
    ) -> AsyncGenerator[Event, None]:
        today = date.today().isoformat()
        out_dir = config.output_dir / today / idea.raw_idea_id
        out_dir.mkdir(parents=True, exist_ok=True)
        image_path = out_dir / "image.png"
        caption_path = out_dir / "caption.txt"

        # 1. Enrich (article + match stats)
        enriched = self._enrich_safely(idea)

        # 2. Researcher — always runs when data_needed is set (kit colours, goal timelines,
        # current player names); also runs when article is too thin to be useful.
        researcher_notes: str | None = None
        if idea.data_needed or len(enriched.article_text) < _ARTICLE_TEXT_MIN_LENGTH:
            logger.info("  article too short — running researcher")
            query = self._build_researcher_query(enriched)
            yield self._state_event(ctx, {"researcher_query": query})
            text_chunks: list[str] = []
            try:
                async for event in researcher_agent.run_async(ctx):
                    yield event
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if getattr(part, "text", None):
                                text_chunks.append(part.text)
            except Exception as e:
                logger.warning("researcher failed: %s", e)
            researcher_notes = "".join(text_chunks).strip() or None

        # 3. Content planner (LLM, with retry)
        yield self._state_event(
            ctx,
            {"enriched_post_json": self._build_planner_input(enriched, researcher_notes)},
        )
        last_planner_error: Exception | None = None
        for attempt in range(1, _PLANNER_MAX_ATTEMPTS + 1):
            ctx.session.state.pop("post_plan", None)
            try:
                async for event in content_planner_agent.run_async(ctx):
                    yield event
                if ctx.session.state.get("post_plan"):
                    last_planner_error = None
                    break
                last_planner_error = RuntimeError("planner returned no post_plan")
            except Exception as e:
                last_planner_error = e
                logger.warning(
                    "planner attempt %d/%d failed: %s",
                    attempt, _PLANNER_MAX_ATTEMPTS, e,
                )
            if attempt < _PLANNER_MAX_ATTEMPTS:
                await asyncio.sleep(_PLANNER_RETRY_SLEEP_S)
        if last_planner_error is not None:
            raise last_planner_error

        post_plan = PostPlan(**ctx.session.state["post_plan"])

        # 4. Image generation (gpt-image-2) — retry once on timeout
        last_img_error: Exception | None = None
        for img_attempt in range(1, _IMAGE_GEN_MAX_ATTEMPTS + 1):
            try:
                bg = await asyncio.to_thread(self._generate_background, post_plan.image_prompt)
                last_img_error = None
                break
            except Exception as e:
                last_img_error = e
                logger.warning(
                    "image gen attempt %d/%d failed: %s",
                    img_attempt, _IMAGE_GEN_MAX_ATTEMPTS, e,
                )
                if img_attempt < _IMAGE_GEN_MAX_ATTEMPTS:
                    await asyncio.sleep(_IMAGE_GEN_RETRY_SLEEP_S)
        if last_img_error is not None:
            raise last_img_error

        # 5. Compositor (PIL)
        await asyncio.to_thread(composite, bg, post_plan.overlay_spec, image_path)
        logger.info("  image written: %s", image_path)

        # 6. Caption writer (LLM)
        yield self._state_event(
            ctx,
            {"caption_input_json": self._build_caption_input(enriched, post_plan)},
        )
        ctx.session.state.pop("caption_output", None)
        async for event in caption_writer_agent.run_async(ctx):
            yield event

        caption_raw = ctx.session.state.get("caption_output", {})
        caption = caption_raw.get("caption", "") if isinstance(caption_raw, dict) else str(caption_raw)
        if not caption:
            raise RuntimeError("caption_writer produced empty caption")
        caption_path.write_text(caption, encoding="utf-8")

        final_posts.append(
            FinalPost(
                idea_id=idea.raw_idea_id,
                image_path=str(image_path),
                caption=caption,
                priority=idea.priority,
                overlay_spec=post_plan.overlay_spec,
            ).model_dump(mode="json")
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _state_event(self, ctx: InvocationContext, delta: dict[str, Any]) -> Event:
        return Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            actions=EventActions(state_delta=delta),
        )

    def _enrich_safely(self, idea: ApprovedIdea) -> EnrichedPost:
        try:
            fd_token = config.football_data_token()
        except EnvironmentError:
            fd_token = None
        try:
            return enrich(idea, fd_token)
        except Exception as e:
            # Enricher's own try/excepts catch network errors, but be defensive:
            # never let an enrichment hiccup poison the planner step — return
            # an EnrichedPost with empty article_text and let the researcher kick in.
            logger.warning("enrich failed for %s: %s", idea.raw_idea_id, e)
            return EnrichedPost(
                idea_id=idea.raw_idea_id,
                content_direction=idea.content_direction,
                data_needed=idea.data_needed,
                source_url=idea.source_url,
                priority=idea.priority,
                article_text="",
                article_image_url=None,
                match_stats=None,
            )

    @staticmethod
    def _build_researcher_query(enriched: EnrichedPost) -> str:
        parts = [f"Story brief: {enriched.content_direction}"]
        if enriched.source_url:
            parts.append(f"Source URL: {enriched.source_url}")
        if enriched.data_needed:
            parts.append(f"Data needed: {', '.join(enriched.data_needed)}")
        return "\n".join(parts)

    @staticmethod
    def _build_planner_input(
        enriched: EnrichedPost, researcher_notes: str | None
    ) -> str:
        payload: dict[str, Any] = {
            "idea_id": enriched.idea_id,
            "content_direction": enriched.content_direction,
            "data_needed": enriched.data_needed,
            "article_text": enriched.article_text[:10000],
            "article_image_url": enriched.article_image_url,
            "match_stats": enriched.match_stats,
            "extra_stats": enriched.extra_stats,
            "researcher_notes": researcher_notes,
        }
        return json.dumps(payload, indent=2, default=str)

    @staticmethod
    def _build_caption_input(enriched: EnrichedPost, post_plan: PostPlan) -> str:
        payload = {
            "content_direction": enriched.content_direction,
            "overlay_spec": post_plan.overlay_spec.model_dump(),
            "article_text": enriched.article_text[:4000],
        }
        return json.dumps(payload, indent=2, default=str)

    @staticmethod
    def _generate_background(image_prompt: str) -> Image.Image:
        client = OpenAI(api_key=config.openai_api_key(), timeout=_IMAGE_GEN_TIMEOUT_S)
        response = client.images.generate(
            model=config.models.image_generator,
            prompt=image_prompt,
            size="1024x1536",
            quality="high",
            n=1,
        )
        img_bytes = base64.b64decode(response.data[0].b64_json)
        return Image.open(io.BytesIO(img_bytes))

    @staticmethod
    def _write_manifest(final_posts: list[dict]) -> None:
        if not final_posts:
            return
        today = date.today().isoformat()
        manifest = config.output_dir / f"{today}_posts.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(final_posts, indent=2, default=str), encoding="utf-8")
        logger.info("wrote manifest: %s (%d posts)", manifest, len(final_posts))


content_generator_agent = ContentGeneratorAgent(name="content_generator_agent")
