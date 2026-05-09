"""Deploy the football content agent to Vertex AI Agent Engine.

Usage:
    .venv/Scripts/python deploy.py

Reads GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION from .env (local) or
environment variables (CI). If AGENT_ENGINE_RESOURCE_NAME is set, updates the
existing resource in place; otherwise creates a new one and prints the name.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION = os.environ["GOOGLE_CLOUD_LOCATION"]

# Agent Engine needs a GCS path to stage the packaged code before deployment.
# We reuse the existing bucket under a dedicated prefix.
STAGING_BUCKET = "gs://football-ig-post-images"

SERVICE_ACCOUNT = f"football-content-agent-sa@{PROJECT}.iam.gserviceaccount.com"

# Runtime dependencies installed in the Agent Engine container.
# Excludes packages pre-installed in the base image (vertexai, google-generativeai).
_REQUIREMENTS = [
    "google-adk==1.31.1",
    "google-cloud-aiplatform==1.148.1",
    "google-cloud-secret-manager==2.27.0",
    "google-cloud-storage==2.19.0",
    "openai==2.32.0",
    "Pillow==12.2.0",
    "pydantic==2.13.3",
    "python-dotenv==1.2.2",
    "requests==2.33.1",
    "feedparser==6.0.12",
    "cloudpickle==3.1.2",
]

import vertexai
import vertexai.agent_engines as agent_engines

from app.pipeline_app import FootballPipelineApp

# Point the Vertex AI SDK at our project and region, and tell it where to
# stage the deployment package before uploading to Agent Engine.
vertexai.init(project=PROJECT, location=LOCATION, staging_bucket=STAGING_BUCKET)

# FootballPipelineApp implements query() — the method Agent Engine calls when
# it receives an HTTP POST to the :query endpoint (e.g. from Cloud Scheduler).
# AdkApp was designed for conversational agents and only exposes session
# management methods, not query() — so we use our own wrapper instead.
app = FootballPipelineApp()

_DEPLOY_KWARGS = dict(
    agent_engine=app,
    requirements=_REQUIREMENTS,
    extra_packages=["app/"],
    display_name="football-content-agent",
    env_vars={
        "AGENT_ENGINE": "1",
        "GOOGLE_GENAI_USE_VERTEXAI": "TRUE",
    },
)

EXISTING_RESOURCE_NAME = os.environ.get("AGENT_ENGINE_RESOURCE_NAME")

print(f"Deploying to project={PROJECT} location={LOCATION} ...")
print(f"Service account: {SERVICE_ACCOUNT}")

if EXISTING_RESOURCE_NAME:
    print(f"Updating existing resource: {EXISTING_RESOURCE_NAME}")
    remote_app = agent_engines.get(EXISTING_RESOURCE_NAME)
    remote_app.update(**_DEPLOY_KWARGS)
else:
    print("No existing resource — creating new deployment ...")
    remote_app = agent_engines.create(**_DEPLOY_KWARGS, service_account=SERVICE_ACCOUNT)

print(f"\nDeployed successfully.")
print(f"Resource name: {remote_app.resource_name}")
print(f"Agent Engine ID: {remote_app.resource_name.split('/')[-1]}")
if not EXISTING_RESOURCE_NAME:
    print(f"\nFirst deployment — add this GitHub Actions secret:")
    print(f"  AGENT_ENGINE_RESOURCE_NAME = {remote_app.resource_name}")
