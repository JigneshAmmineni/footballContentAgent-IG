import json

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext

from app.config import config
from app.models import CandidateIdeaList


def _stage_candidates_as_json(callback_context: CallbackContext) -> None:
    """Stage state["candidate_ideas"] as a JSON string for the ranker prompt.

    The ranker's instruction has a `{candidate_ideas_json}` placeholder. ADK's
    state-injection only does `str(value)` on dicts, which yields Python repr
    (single quotes), not JSON. So we serialise here, after the judge writes
    its structured output, and before the ranker's prompt is built.
    """
    candidates = callback_context.state.get("candidate_ideas")
    if candidates is None:
        return
    callback_context.state["candidate_ideas_json"] = json.dumps(
        candidates, indent=2, default=str
    )


idea_judge_agent = LlmAgent(
    name="idea_judge_agent",
    model=config.models.idea_judge,
    instruction=config.load_prompt("idea_judge"),
    output_schema=CandidateIdeaList,
    output_key="candidate_ideas",
    after_agent_callback=_stage_candidates_as_json,
)
