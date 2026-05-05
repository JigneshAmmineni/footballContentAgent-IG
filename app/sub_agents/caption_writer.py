from pydantic import BaseModel
from google.adk.agents import LlmAgent
from app.config import config


class CaptionOutput(BaseModel):
    caption: str


caption_writer_agent = LlmAgent(
    name="caption_writer_agent",
    model=config.models.caption_writer,
    instruction=config.load_prompt("caption_writer"),
    output_schema=CaptionOutput,
    output_key="caption_output",
)
