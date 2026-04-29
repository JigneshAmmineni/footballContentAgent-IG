from google.adk.agents import LlmAgent

from app.config import config
from app.models.final_post import FinalPostList

caption_critic_agent = LlmAgent(
    name="caption_critic_agent",
    model=config.models.caption_critic,
    instruction=config.load_prompt("caption_critic"),
    output_schema=FinalPostList,
    output_key="final_posts",
)
