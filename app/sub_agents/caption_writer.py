from google.adk.agents import LlmAgent

from app.config import config

_instruction = config.load_prompt("caption_writer").replace(
    "{brand_voice}", config.load_prompt("brand_voice")
)

caption_writer_agent = LlmAgent(
    name="caption_writer_agent",
    model=config.models.caption_writer,
    instruction=_instruction,
    output_key="draft_captions",
)
