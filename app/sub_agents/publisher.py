"""PublisherAgent — for each final post, uploads the image to GCS and publishes to Instagram.

Reads  state["final_posts"]  (written by ContentGeneratorAgent).
Writes state["published_posts"]: list[dict] with gcs_url and instagram_media_id.

Per-post try/except boundary: one failed post does not block the rest.
Skips publishing entirely (with a warning) if credentials are not configured.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions

from app.config import config
from app.tools.gcs import upload_image
from app.tools.instagram import post_to_instagram

logger = logging.getLogger(__name__)


class PublisherAgent(BaseAgent):
    """Uploads images to GCS and publishes each post to Instagram."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        final_posts = ctx.session.state.get("final_posts") or []
        if not final_posts:
            logger.warning("no final_posts in state; nothing to publish")
            yield self._state_event(ctx, {"published_posts": []})
            return

        try:
            bucket = config.gcs_bucket_name()
            ig_user_id = config.instagram_user_id()
            ig_token = config.instagram_access_token()
        except EnvironmentError as e:
            logger.warning("publisher credentials not configured (%s) — skipping publish", e)
            yield self._state_event(ctx, {"published_posts": []})
            return

        published: list[dict] = []
        for post in final_posts:
            idea_id = post["idea_id"]
            image_path = Path(post["image_path"])
            caption = post["caption"]
            try:
                blob_name = f"posts/{image_path.parent.name}/image.png"
                public_url = await asyncio.to_thread(
                    upload_image, image_path, bucket, blob_name
                )
                logger.info("  gcs upload %s → %s", idea_id[:12], public_url)

                media_id = await asyncio.to_thread(
                    post_to_instagram, ig_user_id, ig_token, public_url, caption
                )
                logger.info("  instagram published %s → media_id=%s", idea_id[:12], media_id)

                published.append({
                    "idea_id": idea_id,
                    "gcs_url": public_url,
                    "instagram_media_id": media_id,
                })
            except Exception as e:
                logger.exception("failed to publish post %s: %s", idea_id, e)

        yield self._state_event(ctx, {"published_posts": published})

    def _state_event(self, ctx: InvocationContext, delta: dict[str, Any]) -> Event:
        return Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            actions=EventActions(state_delta=delta),
        )


publisher_agent = PublisherAgent(name="publisher_agent")
