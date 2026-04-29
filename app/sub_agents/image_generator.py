import json
import logging
from datetime import date
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool, ToolContext

from app.config import config
from app.models.approved_idea import ApprovedIdea
from app.tools.image.router import route, GeneratorPath
from app.tools.image.sourcing import get_background_image
from app.tools.image.composite import composite, Overlay
from app.tools.image.pillow_renderer import (
    render_quote_card,
    render_milestone_card,
    render_match_card,
    render_form_dots,
)
from app.tools.image.chart_renderer import render_chart_figure

logger = logging.getLogger(__name__)


def generate_image_for_idea(idea_id: str, content_direction: str, source_url: str = "") -> str:
    """Generate an image for one approved idea. Returns the saved image path as a string.

    Routes to the correct renderer based on content_direction keywords,
    composites the result, and saves to out/YYYY-MM-DD/{idea_id}/image.png.
    """
    today = date.today().isoformat()
    output_path = config.output_dir / today / idea_id / "image.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    path = route(content_direction)
    url = source_url if source_url else None
    logger.info("generate_image_for_idea idea_id=%s route=%s", idea_id, path.name)

    if path == GeneratorPath.CHART:
        fig = render_chart_figure(
            data={"params": [], "values_a": [], "values_b": [], "label_a": idea_id, "label_b": ""},
            chart_type="bar",
        )
        background = get_background_image(url, content_direction)
        composite(background, fig, [], output_path)

    elif path == GeneratorPath.PILLOW:
        background = get_background_image(url, content_direction)
        lower = content_direction.lower()
        if any(w in lower for w in ("quote", "said", "press conference")):
            render_quote_card(background, content_direction, "", output_path)
        elif any(w in lower for w in ("vs", "preview", "fixture", "result", "won", "drew", "lost")):
            render_match_card(None, None, "", "", content_direction[:20], "", output_path)
        else:
            render_milestone_card(background, content_direction[:80], "", output_path)

    else:  # IMAGEN
        from app.tools.image.sourcing import _imagen_fallback
        img = _imagen_fallback(content_direction, (1080, 1080))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, format="PNG")

    logger.info("Image saved to %s", output_path)
    return str(output_path)


def get_image_paths_from_state(tool_context: ToolContext) -> dict[str, str]:
    """Process all approved ideas from session state and return a mapping of idea_id -> image_path."""
    raw = tool_context.state.get("approved_ideas", {})
    ideas_data = json.loads(raw) if isinstance(raw, str) else raw
    ideas_list = ideas_data.get("ideas", []) if isinstance(ideas_data, dict) else ideas_data

    logger.info("get_image_paths_from_state processing %d ideas", len(ideas_list))

    image_paths = {}
    for idea_data in ideas_list:
        idea = ApprovedIdea(**idea_data)
        try:
            path = generate_image_for_idea(
                idea_id=idea.raw_idea_id,
                content_direction=idea.content_direction,
                source_url=idea.source_url or "",
            )
            image_paths[idea.raw_idea_id] = path
        except Exception as exc:
            logger.error("Image generation FAILED for idea_id=%s: %s", idea.raw_idea_id, exc)
            image_paths[idea.raw_idea_id] = ""

    succeeded = sum(1 for v in image_paths.values() if v)
    logger.info("Image generation complete: %d/%d succeeded", succeeded, len(ideas_list))
    return image_paths


image_generator_agent = LlmAgent(
    name="image_generator_agent",
    model=config.models.image_generator,
    instruction=config.load_prompt("image_generator"),
    tools=[
        FunctionTool(func=generate_image_for_idea),
        FunctionTool(func=get_image_paths_from_state),
    ],
    output_key="image_paths",
)
