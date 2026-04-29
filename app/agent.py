import logging

from google.adk.agents import SequentialAgent

from app.agent_logging import (
    setup_run_logger,
    log_before_idea_judge,
    log_after_idea_judge,
    log_after_image_generator,
    log_before_caption_writer,
    log_after_caption_writer,
    log_before_caption_critic,
    log_after_caption_critic,
)
from app.callbacks import write_output_files
from app.sub_agents.news_ingest import NewsIngestAgent
from app.sub_agents.idea_judge import idea_judge_agent
from app.sub_agents.image_generator import image_generator_agent
from app.sub_agents.caption_writer import caption_writer_agent
from app.sub_agents.caption_critic import caption_critic_agent

setup_run_logger()

idea_judge_agent.before_agent_callback = log_before_idea_judge
idea_judge_agent.after_agent_callback = log_after_idea_judge

image_generator_agent.after_agent_callback = log_after_image_generator

caption_writer_agent.before_agent_callback = log_before_caption_writer
caption_writer_agent.after_agent_callback = log_after_caption_writer

caption_critic_agent.before_agent_callback = log_before_caption_critic
caption_critic_agent.after_agent_callback = log_after_caption_critic

root_agent = SequentialAgent(
    name="football_content_pipeline",
    description=(
        "Daily pipeline that ingests football news and stats, judges ideas for "
        "Instagram post-worthiness, generates images and hype captions, and outputs "
        "ready-to-post content for the Big 5 European leagues."
    ),
    sub_agents=[
        NewsIngestAgent(name="news_ingest_agent"),
        idea_judge_agent,
        image_generator_agent,
        caption_writer_agent,
        caption_critic_agent,
    ],
    after_agent_callback=write_output_files,
)
