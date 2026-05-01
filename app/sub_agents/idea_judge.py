from google.adk.agents import LlmAgent
from app.config import config
from app.models import ApprovedIdeaList

idea_judge_agent = LlmAgent(
    name="idea_judge_agent",
    model=config.models.idea_judge,
    instruction=config.load_prompt("idea_judge"),
    output_schema=ApprovedIdeaList,
    output_key="approved_ideas",
)
