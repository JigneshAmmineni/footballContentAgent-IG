"""Logging callbacks for each LlmAgent — log state going in and coming out."""
import json
import logging
from pathlib import Path

from google.adk.agents.callback_context import CallbackContext

logger = logging.getLogger(__name__)

_AUDIT_LOG = Path(__file__).parent.parent / "scratch" / "last_run.log"


def setup_run_logger():
    """Called once at startup. Attaches a fresh file handler to the app logger."""
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.DEBUG)

    _AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(_AUDIT_LOG, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s  %(name)-40s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    ))
    app_logger.addHandler(fh)

    # Also surface app logs on the console at INFO
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(name)-30s  %(levelname)-7s  %(message)s"))
    app_logger.addHandler(ch)

    app_logger.info("Audit log -> %s", _AUDIT_LOG)


def _safe_parse(raw) -> object:
    """Parse state value: already a dict/list, a JSON string, or empty → {}."""
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _dump(label: str, data) -> None:
    """Write full JSON to the audit log (DEBUG so it doesn't flood the console)."""
    logger.debug("%s\n%s", label, json.dumps(data, indent=2, default=str))


# ── idea_judge ────────────────────────────────────────────────────────────────

def log_before_idea_judge(callback_context: CallbackContext):
    ideas = _safe_parse(callback_context.state.get("raw_ideas", []))
    if isinstance(ideas, dict):
        ideas = ideas.get("ideas", [])
    logger.info("[idea_judge] INPUT: %d raw ideas", len(ideas))
    _dump("[idea_judge] raw_ideas FULL", ideas)
    return None


def log_after_idea_judge(callback_context: CallbackContext):
    data = _safe_parse(callback_context.state.get("approved_ideas", {}))
    ideas = data.get("ideas", []) if isinstance(data, dict) else []
    logger.info(
        "[idea_judge] OUTPUT: %d approved ideas | priorities: %s",
        len(ideas),
        [i.get("priority") for i in ideas],
    )
    _dump("[idea_judge] approved_ideas FULL", data)


# ── image_generator ───────────────────────────────────────────────────────────

def log_after_image_generator(callback_context: CallbackContext):
    paths = _safe_parse(callback_context.state.get("image_paths", {}))
    if not isinstance(paths, dict):
        paths = {}
    ok = sum(1 for v in paths.values() if v)
    logger.info("[image_generator] OUTPUT: %d/%d images generated", ok, len(paths))
    _dump("[image_generator] image_paths FULL", paths)


# ── caption_writer ────────────────────────────────────────────────────────────

def log_before_caption_writer(callback_context: CallbackContext):
    data = _safe_parse(callback_context.state.get("approved_ideas", {}))
    ideas = data.get("ideas", []) if isinstance(data, dict) else []
    logger.info("[caption_writer] INPUT: %d ideas to caption", len(ideas))
    return None


def log_after_caption_writer(callback_context: CallbackContext):
    captions = _safe_parse(callback_context.state.get("draft_captions", {}))
    if not isinstance(captions, dict):
        captions = {}
    logger.info("[caption_writer] OUTPUT: %d draft captions", len(captions))
    _dump("[caption_writer] draft_captions FULL", captions)


# ── caption_critic ────────────────────────────────────────────────────────────

def log_before_caption_critic(callback_context: CallbackContext):
    captions = _safe_parse(callback_context.state.get("draft_captions", {}))
    if not isinstance(captions, dict):
        captions = {}
    logger.info("[caption_critic] INPUT: %d draft captions to review", len(captions))
    return None


def log_after_caption_critic(callback_context: CallbackContext):
    data = _safe_parse(callback_context.state.get("final_posts", {}))
    posts = data.get("posts", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    logger.info("[caption_critic] OUTPUT: %d final posts", len(posts))
    _dump("[caption_critic] final_posts FULL", data)
