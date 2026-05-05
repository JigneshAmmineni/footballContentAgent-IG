"""Content generation pipeline: approved.json -> out/ posts.

For each approved idea:
  1. Enrich: Jina Reader (article text) + football-data.org (match stats)
  2. Content planner (LLM) -> PostPlan (OverlaySpec + image_prompt)
  3. gpt-image-2 -> background image (cinematic, no text)
  4. PIL compositor -> final image (background + overlay)
  5. Caption writer (LLM) -> Instagram caption
  6. Save to out/{YYYY-MM-DD}/{idea_id}/image.png + caption.txt

Usage:
    .venv/Scripts/python scratch/run_content.py
    .venv/Scripts/python scratch/run_content.py --idea <idea_id>
"""
import argparse
import io
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import base64
from google.genai import types as genai_types
from openai import OpenAI
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from PIL import Image

from app.config import config
from app.models import ApprovedIdea, PostPlan, FinalPost
from app.tools.enricher import enrich
from app.tools.compositor import composite
from app.sub_agents.content_planner import content_planner_agent
from app.sub_agents.caption_writer import caption_writer_agent
from app.sub_agents.researcher import researcher_agent

APPROVED = Path(__file__).parent / "approved.json"


def _run_agent_text(agent, app_name: str, payload_text: str) -> str:
    """Run an agent without output_schema and return its final text response."""
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)
    session = session_service.create_session_sync(app_name=app_name, user_id="local")
    message = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=payload_text)],
    )
    last_text = ""
    for event in runner.run(user_id="local", session_id=session.id, new_message=message):
        if hasattr(event, "content") and event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    last_text = part.text
    return last_text


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


_ARTICLE_TEXT_MIN_LENGTH = 300  # below this we treat the fetch as failed and run the researcher


def _maybe_run_researcher(
    content_direction: str,
    article_text: str,
    source_url: str | None = None,
    data_needed: list[str] | None = None,
) -> str | None:
    """Return researcher notes if article_text is too short to be useful, else None."""
    if len(article_text) >= _ARTICLE_TEXT_MIN_LENGTH:
        return None
    print("\n  --- RESEARCHER (article blocked — running web search fallback) ---")
    context = f"Story brief: {content_direction}"
    if source_url:
        context += f"\nSource URL: {source_url}"
    if data_needed:
        context += f"\nData needed: {', '.join(data_needed)}"
    notes = _run_agent_text(
        researcher_agent,
        "researcher",
        f"Find current information about this football story:\n\n{context}",
    )
    _log("researcher_notes", notes)
    return notes or None


def _generate_background(image_prompt: str) -> Image.Image:
    client = OpenAI(api_key=config.openai_api_key())
    response = client.images.generate(
        model=config.models.image_generator,  # "gpt-image-2"
        prompt=image_prompt,
        size="1024x1536",  # portrait; compositor resizes to 1080x1350
        quality="high",
        n=1,
    )
    img_bytes = base64.b64decode(response.data[0].b64_json)
    return Image.open(io.BytesIO(img_bytes))


def _log(label: str, value: str = "", *, indent: int = 4) -> None:
    pad = " " * indent
    print(f"{pad}[{label}]")
    if value:
        for line in value.splitlines():
            print(f"{pad}  {line}")


def process_idea(idea: ApprovedIdea) -> FinalPost:
    today = date.today().isoformat()
    out_dir = config.output_dir / today / idea.raw_idea_id
    out_dir.mkdir(parents=True, exist_ok=True)
    image_path = out_dir / "image.png"
    caption_path = out_dir / "caption.txt"

    # ------------------------------------------------------------------ #
    # Step 1: Enrich
    # ------------------------------------------------------------------ #
    print("\n  --- STEP 1: ENRICHMENT ---")
    try:
        fd_token = config.football_data_token()
    except EnvironmentError:
        fd_token = None
    enriched = enrich(idea, fd_token)

    _log("article_text",
         f"{len(enriched.article_text)} chars fetched via Jina Reader"
         + (f" | first image: {enriched.article_image_url}" if enriched.article_image_url else " | no image found"))
    if enriched.match_stats:
        home = enriched.match_stats.get("homeTeam", {}).get("name", "?")
        away = enriched.match_stats.get("awayTeam", {}).get("name", "?")
        score = enriched.match_stats.get("score", {}).get("fullTime", {})
        _log("match_stats", f"football-data.org match found: {home} {score.get('home')} - {score.get('away')} {away}")
    else:
        _log("match_stats", "None (either not needed or not found)")

    researcher_notes = _maybe_run_researcher(enriched.content_direction, enriched.article_text, enriched.source_url, enriched.data_needed)

    # ------------------------------------------------------------------ #
    # Step 2: Content planner -> PostPlan
    # ------------------------------------------------------------------ #
    print("\n  --- STEP 2: CONTENT PLANNER (LLM) ---")
    planner_input = {
        "idea_id": enriched.idea_id,
        "content_direction": enriched.content_direction,
        "data_needed": enriched.data_needed,
        "article_text": enriched.article_text[:10000],  # cap to stay within token budget
        "article_image_url": enriched.article_image_url,
        "match_stats": enriched.match_stats,
        "extra_stats": enriched.extra_stats,
        "researcher_notes": researcher_notes,
    }
    _log("LLM input", f"content_direction: {enriched.content_direction}")
    _log("LLM input", f"data_needed: {enriched.data_needed}")
    _log("LLM input", f"article_text length sent: {len(planner_input['article_text'])} chars")
    _log("LLM input", f"match_stats present: {enriched.match_stats is not None}")
    _log("LLM input", f"researcher_notes present: {researcher_notes is not None}")

    plan_state = _run_agent(
        content_planner_agent,
        "content_planner",
        f"Plan the content for this enriched post:\n\n{json.dumps(planner_input, indent=2, default=str)}",
    )
    raw_plan = plan_state.get("post_plan", {})
    post_plan = PostPlan(**raw_plan)

    spec = post_plan.overlay_spec
    _log("LLM output: layout", spec.layout)
    _log("LLM output: header", spec.header)
    if spec.left_label:
        _log("LLM output: left_label", spec.left_label)
    if spec.right_label:
        _log("LLM output: right_label", spec.right_label)
    if spec.center_text:
        _log("LLM output: center_text", spec.center_text)
    if spec.rows:
        _log("LLM output: rows", "\n".join(
            f"  side={r.side}  label={r.label!r}  value={r.value!r}" for r in spec.rows
        ))
    if spec.footer:
        _log("LLM output: footer", spec.footer)
    _log("LLM output: image_prompt", post_plan.image_prompt)

    # ------------------------------------------------------------------ #
    # Step 3: Generate background image
    # ------------------------------------------------------------------ #
    print("\n  --- STEP 3: IMAGE GENERATION (gpt-image-2) ---")
    _log("prompt sent to gpt-image-2", post_plan.image_prompt)
    bg = _generate_background(post_plan.image_prompt)
    _log("background", f"downloaded: {bg.size[0]}x{bg.size[1]} px")

    # ------------------------------------------------------------------ #
    # Step 4: PIL compositor
    # ------------------------------------------------------------------ #
    print("\n  --- STEP 4: COMPOSITOR (PIL) ---")
    composite(bg, post_plan.overlay_spec, image_path)
    _log("output", f"written to {image_path}")

    # ------------------------------------------------------------------ #
    # Step 5: Caption writer
    # ------------------------------------------------------------------ #
    print("\n  --- STEP 5: CAPTION WRITER (LLM) ---")
    caption_input = {
        "content_direction": enriched.content_direction,
        "overlay_spec": post_plan.overlay_spec.model_dump(),
        "article_text": enriched.article_text[:4000],
    }
    caption_state = _run_agent(
        caption_writer_agent,
        "caption_writer",
        f"Write an Instagram caption for this post:\n\n{json.dumps(caption_input, indent=2, default=str)}",
    )
    raw_caption = caption_state.get("caption_output", {})
    caption = raw_caption.get("caption", "") if isinstance(raw_caption, dict) else str(raw_caption)
    _log("LLM output: caption", caption)
    caption_path.write_text(caption, encoding="utf-8")

    return FinalPost(
        idea_id=idea.raw_idea_id,
        image_path=str(image_path),
        caption=caption,
        priority=idea.priority,
        overlay_spec=post_plan.overlay_spec,
    )


def process_plan_only(idea: ApprovedIdea) -> None:
    """Run only Steps 1-2 (enrichment + content planner) and print the PostPlan."""
    try:
        fd_token = config.football_data_token()
    except EnvironmentError:
        fd_token = None

    print("\n  --- STEP 1: ENRICHMENT ---")
    enriched = enrich(idea, fd_token)
    _log("article_text",
         f"{len(enriched.article_text)} chars"
         + (f" | image: {enriched.article_image_url}" if enriched.article_image_url else " | no image"))
    if enriched.match_stats:
        home = enriched.match_stats.get("homeTeam", {}).get("name", "?")
        away = enriched.match_stats.get("awayTeam", {}).get("name", "?")
        score = enriched.match_stats.get("score", {}).get("fullTime", {})
        _log("match_stats", f"{home} {score.get('home')} - {score.get('away')} {away}")
    else:
        _log("match_stats", "None")

    researcher_notes = _maybe_run_researcher(enriched.content_direction, enriched.article_text, enriched.source_url, enriched.data_needed)

    print("\n  --- STEP 2: CONTENT PLANNER (LLM) ---")
    planner_input = {
        "idea_id": enriched.idea_id,
        "content_direction": enriched.content_direction,
        "data_needed": enriched.data_needed,
        "article_text": enriched.article_text[:10000],
        "article_image_url": enriched.article_image_url,
        "match_stats": enriched.match_stats,
        "extra_stats": enriched.extra_stats,
        "researcher_notes": researcher_notes,
    }
    plan_state = _run_agent(
        content_planner_agent,
        "content_planner",
        f"Plan the content for this enriched post:\n\n{json.dumps(planner_input, indent=2, default=str)}",
    )
    raw_plan = plan_state.get("post_plan", {})
    post_plan = PostPlan(**raw_plan)

    spec = post_plan.overlay_spec
    print("\n  -- OverlaySpec --")
    _log("layout", spec.layout)
    _log("header", spec.header)
    if spec.left_label:  _log("left_label", spec.left_label)
    if spec.right_label: _log("right_label", spec.right_label)
    if spec.center_text: _log("center_text", spec.center_text)
    if spec.rows:
        _log("rows", "\n".join(
            f"side={r.side}  label={r.label!r}  value={r.value!r}" for r in spec.rows
        ))
    if spec.footer: _log("footer", spec.footer)

    print("\n  -- image_prompt --")
    print(f"    {post_plan.image_prompt}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--idea", help="Process a single idea by raw_idea_id")
    parser.add_argument("--plan-only", action="store_true",
                        help="Stop after content planner (Steps 1-2). No image generation.")
    args = parser.parse_args()

    raw = json.loads(APPROVED.read_text(encoding="utf-8"))
    ideas = [ApprovedIdea(**r) for r in raw]

    if args.idea:
        ideas = [i for i in ideas if i.raw_idea_id == args.idea]
        if not ideas:
            print(f"Idea {args.idea!r} not found in approved.json")
            sys.exit(1)

    _INTER_IDEA_SLEEP = 30  # seconds between ideas — lets Gemini/OpenAI rate limits recover

    print(f"Processing {len(ideas)} idea(s)...")
    results = []
    for i, idea in enumerate(ideas):
        if i > 0:
            print(f"\n  [sleeping {_INTER_IDEA_SLEEP}s before next idea...]")
            time.sleep(_INTER_IDEA_SLEEP)
        print(f"\n[priority={idea.priority}] {idea.content_direction[:70]}...")
        try:
            if args.plan_only:
                process_plan_only(idea)
            else:
                post = process_idea(idea)
                results.append(post.model_dump())
                print(f"  -> {post.image_path}")
        except Exception as e:
            print(f"  FAILED: {e}")

    today = date.today().isoformat()
    out_file = config.output_dir / f"{today}_posts.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nDone. {len(results)} post(s) saved -> {out_file}")


if __name__ == "__main__":
    main()
