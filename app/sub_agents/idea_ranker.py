from google.adk.agents import LlmAgent
from app.config import config
from app.models import ApprovedIdeaList

idea_ranker_agent = LlmAgent(
    name="idea_ranker_agent",
    model=config.models.idea_ranker,
    instruction=config.load_prompt("idea_ranker"),
    output_schema=ApprovedIdeaList,
    output_key="approved_ideas",
)
