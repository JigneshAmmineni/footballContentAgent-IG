"""Deploy the football content agent to Vertex AI Agent Engine.

Usage:
    .venv/Scripts/python deploy.py

Reads GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION from .env.
Prints the deployed resource name on success — save it for Cloud Scheduler.
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

print(f"Deploying to project={PROJECT} location={LOCATION} ...")
print(f"Service account: {SERVICE_ACCOUNT}")

remote_app = agent_engines.create(
    agent_engine=app,
    # Pip packages installed in the container at deployment time.
    requirements=_REQUIREMENTS,
    # Local directories/packages bundled into the deployment artifact.
    # app/ is a Python package (has __init__.py) — it gets zipped, uploaded
    # to the staging bucket, then installed in the container alongside the
    # pip requirements above.
    extra_packages=["app/"],
    display_name="football-content-agent",
    # Non-secret config injected as environment variables in the container.
    # AGENT_ENGINE=1 is the flag our code checks to switch on GCS paths and
    # Secret Manager instead of local .env + local filesystem.
    env_vars={
        "AGENT_ENGINE": "1",
        "GOOGLE_GENAI_USE_VERTEXAI": "TRUE",
    },
    # The IAM service account the container runs as — this is the identity
    # that has secretAccessor, storage.objectAdmin, and aiplatform.user.
    service_account=SERVICE_ACCOUNT,
)

print(f"\nDeployed successfully.")
print(f"Resource name: {remote_app.resource_name}")
print(f"Agent Engine ID: {remote_app.resource_name.split('/')[-1]}")
print(f"\nSave this resource name — you need it for Cloud Scheduler.")
