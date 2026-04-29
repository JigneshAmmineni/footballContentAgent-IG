import json
import logging
from datetime import date
from pathlib import Path

from google.adk.agents.callback_context import CallbackContext

from app.config import config
from app.models.final_post import FinalPost

logger = logging.getLogger(__name__)


def write_output_files(callback_context: CallbackContext) -> None:
    """after_agent_callback on root_agent.
    Reads final_posts from session state and writes each post's caption to disk.
    Also archives the full post list as JSON.
    """
    state = callback_context.state
    logger.info("write_output_files: starting")

    raw = state.get("final_posts")
    if not raw:
        logger.warning("write_output_files: final_posts not found in state — skipping output")
        return

    if isinstance(raw, list):
        posts_data = raw
    elif isinstance(raw, dict):
        posts_data = raw.get("posts", [])
    else:
        posts_data = json.loads(raw).get("posts", [])
    posts = [FinalPost(**p) for p in posts_data]
    logger.info("write_output_files: writing %d posts", len(posts))

    today = date.today().isoformat()
    archive_path = config.archive_dir / f"{today}.json"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(
        json.dumps([p.model_dump() for p in posts], indent=2),
        encoding="utf-8",
    )
    logger.info("Archive written to %s", archive_path)

    for post in sorted(posts, key=lambda p: p.priority, reverse=True):
        post_dir = config.output_dir / today / post.idea_id
        post_dir.mkdir(parents=True, exist_ok=True)
        caption_path = post_dir / "caption.txt"
        caption_path.write_text(post.caption, encoding="utf-8")
        logger.info("Caption written: %s (priority=%d)", caption_path, post.priority)
