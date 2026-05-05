from google.adk.agents import LlmAgent
from app.config import config
from app.models import PostPlan

content_planner_agent = LlmAgent(
    name="content_planner_agent",
    model=config.models.content_planner,
    instruction=config.load_prompt("content_planner"),
    output_schema=PostPlan,
    output_key="post_plan",
)
