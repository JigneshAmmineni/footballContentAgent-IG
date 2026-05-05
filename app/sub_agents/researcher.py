from google.adk.agents import LlmAgent
from google.adk.tools import google_search
from app.config import config

researcher_agent = LlmAgent(
    name="researcher_agent",
    model=config.models.news_ingest,  # gemini-2.5-flash — fast, search-capable
    instruction=config.load_prompt("researcher"),
    tools=[google_search],
)
