"""Run image generation + caption writer + caption critic for a single idea.

Bypasses news ingest and idea judge entirely — load a fixture or paste an
ApprovedIdea directly. Useful for iterating on image templates and caption
prompts without running the full pipeline or burning quota.

Usage:
    # Use the first idea from the last judge run
    python scratch/run_single_idea.py

    # Specify an idea by raw_idea_id from scratch/last_raw_ideas.json
    python scratch/run_single_idea.py --id <raw_idea_id>

    # Pass a custom content_direction inline
    python scratch/run_single_idea.py --direction "Bellingham UCL brace vs Bayern — compare G+A to Zidane's first UCL season at Madrid"

    # Skip image generation (caption-only mode)
    python scratch/run_single_idea.py --no-image
"""
import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(name)-35s  %(levelname)-7s  %(message)s",
)
logger = logging.getLogger("run_single_idea")

from google import genai

from app.config import config
from app.models.approved_idea import ApprovedIdea
from app.sub_agents.image_generator import generate_image_for_idea


def _load_approved_ideas() -> list[dict]:
    """Load approved ideas from the last judge run (scratch/last_run.log session state)."""
    # Try the session DB first, fall back to raw ideas
    approved_path = Path(__file__).parent.parent / "scratch" / "last_approved_ideas.json"
    if approved_path.exists():
        return json.loads(approved_path.read_text(encoding="utf-8"))
    return []


def _load_raw_ideas() -> list[dict]:
    raw_path = Path(__file__).parent.parent / "scratch" / "last_raw_ideas.json"
    if raw_path.exists():
        return json.loads(raw_path.read_text(encoding="utf-8"))
    return []


def _make_idea(direction: str, idea_id: str = "test_idea", source_url: str = "") -> ApprovedIdea:
    return ApprovedIdea(
        raw_idea_id=idea_id,
        priority=9,
        content_direction=direction,
        data_needed=[],
        source_url=source_url or None,
    )


def _call_llm(model: str, prompt: str) -> str:
    client = genai.Client(
        vertexai=True,
        project=__import__("os").getenv("GOOGLE_CLOUD_PROJECT"),
        location=__import__("os").getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )
    response = client.models.generate_content(model=model, contents=[prompt])
    return response.text


def run_single_idea(idea: ApprovedIdea, skip_image: bool = False) -> dict:
    result = {"idea_id": idea.raw_idea_id, "content_direction": idea.content_direction}

    # ── 1. Image generation ────────────────────────────────────────────────
    if not skip_image:
        logger.info("Generating image for idea_id=%s", idea.raw_idea_id)
        try:
            image_path = generate_image_for_idea(
                idea_id=idea.raw_idea_id,
                content_direction=idea.content_direction,
                source_url=idea.source_url or "",
            )
            result["image_path"] = image_path
            logger.info("Image saved: %s", image_path)
        except Exception as e:
            logger.error("Image generation failed: %s", e)
            result["image_path"] = None
    else:
        result["image_path"] = None
        logger.info("Skipping image generation (--no-image)")

    # ── 2. Caption writer ──────────────────────────────────────────────────
    logger.info("Writing caption...")
    brand_voice = config.load_prompt("brand_voice")
    caption_writer_prompt = config.load_prompt("caption_writer").replace("{brand_voice}", brand_voice)

    caption_input = json.dumps({idea.raw_idea_id: idea.content_direction}, indent=2)
    draft_prompt = (
        f"{caption_writer_prompt}\n\n"
        f"approved_ideas:\n{caption_input}"
    )

    try:
        draft_raw = _call_llm(config.models.caption_writer, draft_prompt)
        logger.info("Draft caption received (%d chars)", len(draft_raw))
        # Strip markdown code fences if present
        draft_text = draft_raw.strip()
        if draft_text.startswith("```"):
            draft_text = "\n".join(draft_text.split("\n")[1:-1])
        draft_captions = json.loads(draft_text)
        draft = draft_captions.get(idea.raw_idea_id, draft_text)
    except Exception as e:
        logger.error("Caption writer failed: %s", e)
        draft = draft_raw if "draft_raw" in dir() else "(failed)"

    result["draft_caption"] = draft
    logger.info("Draft caption:\n%s", draft)

    # ── 3. Caption critic ──────────────────────────────────────────────────
    logger.info("Running caption critic...")
    critic_prompt_template = config.load_prompt("caption_critic")
    critic_input = json.dumps({
        "approved_ideas": {"ideas": [idea.model_dump()]},
        "draft_captions": {idea.raw_idea_id: draft},
        "image_paths": {idea.raw_idea_id: result.get("image_path", "")},
    }, indent=2)
    critic_prompt = f"{critic_prompt_template}\n\nInput:\n{critic_input}"

    try:
        critic_raw = _call_llm(config.models.caption_critic, critic_prompt)
        logger.info("Critic response received (%d chars)", len(critic_raw))
        critic_text = critic_raw.strip()
        if critic_text.startswith("```"):
            critic_text = "\n".join(critic_text.split("\n")[1:-1])
        critic_data = json.loads(critic_text)
        posts = critic_data.get("posts", [])
        final_caption = posts[0].get("caption", critic_raw) if posts else critic_raw
    except Exception as e:
        logger.error("Caption critic failed: %s", e)
        final_caption = draft

    result["final_caption"] = final_caption
    logger.info("Final caption:\n%s", final_caption)

    return result


def main():
    parser = argparse.ArgumentParser(description="Run a single idea through image + caption pipeline")
    parser.add_argument("--id", help="raw_idea_id from last_raw_ideas.json to use as source")
    parser.add_argument("--direction", help="Custom content_direction string (skips raw ideas lookup)")
    parser.add_argument("--no-image", action="store_true", help="Skip image generation")
    args = parser.parse_args()

    if args.direction:
        idea = _make_idea(args.direction, idea_id=args.id or "custom_idea")
    else:
        # Load from last judge run or raw ideas
        approved = _load_approved_ideas()
        raw = _load_raw_ideas()

        if approved and not args.id:
            idea_data = approved[0]
            idea = ApprovedIdea(**idea_data)
            logger.info("Using first approved idea: %s", idea.raw_idea_id)
        elif args.id and raw:
            match = next((r for r in raw if r["id"] == args.id), None)
            if not match:
                logger.error("id '%s' not found in last_raw_ideas.json", args.id)
                sys.exit(1)
            idea = _make_idea(
                direction=match["content_hint"],
                idea_id=match["id"],
                source_url=match.get("source_url", ""),
            )
        else:
            logger.error(
                "No idea source found. Run dump_samples.py first, or pass --direction."
            )
            sys.exit(1)

    result = run_single_idea(idea, skip_image=args.no_image)

    out_path = Path(__file__).parent / "single_idea_result.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    logger.info("Result written to %s", out_path)


if __name__ == "__main__":
    main()
