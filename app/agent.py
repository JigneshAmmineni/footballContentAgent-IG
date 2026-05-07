"""Root agent for the football content pipeline.

This is the deployable entry point for Vertex AI Agent Engine. The Agent Engine
runtime imports `root_agent` from this module and invokes it for each session.

Pipeline:
    fetcher_agent           — pulls raw ideas from football_data, newsapi,
                              reddit, rss; dedups; writes state["raw_ideas"]
    idea_judge_agent        — filters to ~25 candidates; writes state["candidate_ideas"]
    idea_ranker_agent       — picks top 5 ranked; writes state["approved_ideas"]
    content_generator_agent — per-idea: enrich → plan → image → composite → caption;
                              writes state["final_posts"]
    publisher_agent         — uploads images to GCS, posts to Instagram;
                              writes state["published_posts"]
"""
from google.adk.agents import SequentialAgent

from app.sub_agents.content_generator import content_generator_agent
from app.sub_agents.fetcher import fetcher_agent
from app.sub_agents.idea_judge import idea_judge_agent
from app.sub_agents.idea_ranker import idea_ranker_agent
from app.sub_agents.publisher import publisher_agent

root_agent = SequentialAgent(
    name="football_content_pipeline",
    description=(
        "Daily Instagram content pipeline for Big-5 European football: "
        "fetches news, judges + ranks the top 5 stories, generates "
        "an image and caption for each, then publishes to Instagram."
    ),
    sub_agents=[
        fetcher_agent,
        idea_judge_agent,
        idea_ranker_agent,
        content_generator_agent,
        publisher_agent,
    ],
)
