# Deployment Guide

## Overview

The agent is deployed to **Vertex AI Agent Engine** — Google's managed runtime for ADK agents. Once deployed, it lives as a persistent resource in your GCP project and can be invoked on demand (e.g. by Cloud Scheduler). No container is running between invocations; it spins up per-call and tears down when done.

There are two ways to deploy:
1. **From local files** — running `deploy.py` on your machine (this document)
2. **From GitHub via CI/CD** — a GitHub Actions workflow that runs the same `deploy.py` on every push to `main` (see CI/CD section below)

---

## Local Deployment

### What `deploy.py` does, step by step

**1. `vertexai.init(staging_bucket=...)`**

Before anything is deployed, the Vertex AI SDK needs a GCS path to use as a staging area. It zips your `app/` package and uploads it there so the Agent Engine container can fetch it during provisioning. We reuse the existing `football-ig-post-images` bucket under an `agent-engine-staging/` prefix — no new bucket needed.

**2. `AdkApp(agent=root_agent)`**

Agent Engine speaks a generic "Reasoning Engine" protocol — it sends HTTP invocation requests and expects a structured response. Your `root_agent` is an ADK `SequentialAgent` that speaks the ADK event/session protocol. `AdkApp` is a thin adapter between the two: it wraps your agent and translates Agent Engine's invocation format into ADK's internal machinery. Without it, Agent Engine wouldn't know how to call your pipeline.

**3. `ReasoningEngine.create(...)`**

This is the actual deployment call. It:
- Zips `app/` and uploads it to the staging bucket
- Creates a managed Agent Engine resource in Vertex AI with a stable, permanent resource name (e.g. `projects/123/locations/us-central1/reasoningEngines/456`)
- Records which pip packages to install (`requirements`) and which code to bundle (`extra_packages`)

After this returns, the resource exists in Vertex AI. No container is running yet — it provisions on demand.

**Parameters explained:**

| Parameter | What it does |
|---|---|
| `requirements` | Pip packages installed in the container at deploy time — your runtime dependencies, curated from `requirements.txt` |
| `extra_packages=["app/"]` | Your application code, zipped and installed in the container. Agent Engine doesn't pull from GitHub — the code must be bundled here. This is why `from app.config import config` works inside the container |
| `env_vars` | Non-secret config injected as container environment variables. `AGENT_ENGINE=1` is the flag our code checks to switch on Secret Manager and `/tmp` paths instead of `.env` and local filesystem |
| `service_account` | The IAM identity the container runs as. This SA has `secretAccessor`, `storage.objectAdmin`, and `aiplatform.user` — without it the container can't read secrets, write to GCS, or call Gemini |

**Why `AGENT_ENGINE=1` matters:**

Our code has two runtime modes controlled by this flag:

| | Local (`AGENT_ENGINE` unset) | Agent Engine (`AGENT_ENGINE=1`) |
|---|---|---|
| Secrets | Read from `.env` via `os.getenv` | Fetched from Secret Manager |
| Output images | Written to `out/` at project root | Written to `/tmp/out` (only writable path in container) |
| `seen.json` dedup | Read/written to `data/seen.json` | Read/written to `gs://football-ig-post-images/dedup/seen.json` |

**`service_account` and IAM — how it connects:**

```
Agent Engine container
  → runs as: football-content-agent-sa@PROJECT.iam.gserviceaccount.com
  → which has been granted:
      roles/aiplatform.user          → Gemini API calls
      roles/storage.objectAdmin      → GCS bucket (images + seen.json)
      roles/secretmanager.secretAccessor → read all 8 secrets
```

The service account was created manually (via `gcloud`) before deployment. The `service_account` parameter in `deploy.py` is just telling Agent Engine which existing identity to assume — it doesn't create anything new.

### How to run

```bash
.venv/Scripts/python deploy.py
```

Save the printed resource name — you need it to invoke the agent and to set up Cloud Scheduler.

### Re-deploying after code changes

`ReasoningEngine.create()` creates a **new** resource every time — it does not update an existing one. To update the deployed agent after a code change:

```python
# In a separate update script or interactively:
import vertexai
from vertexai.preview.reasoning_engines import ReasoningEngine

vertexai.init(project=PROJECT, location=LOCATION, staging_bucket=STAGING_BUCKET)
remote_app = ReasoningEngine(resource_name="YOUR_RESOURCE_NAME")
remote_app.update(extra_packages=["app/"])
```

Or delete the old resource and run `deploy.py` again to create a fresh one.

---

## Cloud Scheduler (daily trigger)

Once deployed, you trigger the agent via an HTTP POST to its Agent Engine endpoint. Cloud Scheduler handles the daily cron.

```bash
gcloud scheduler jobs create http football-content-agent-daily \
  --location=us-central1 \
  --schedule="0 8 * * *" \
  --uri="https://us-central1-aiplatform.googleapis.com/v1/YOUR_RESOURCE_NAME:query" \
  --message-body='{"input": {}}' \
  --headers="Content-Type=application/json" \
  --oauth-service-account-email="football-content-agent-sa@PROJECT.iam.gserviceaccount.com"
```

Replace `YOUR_RESOURCE_NAME` with the resource name printed by `deploy.py`. The `--schedule` is standard cron syntax — `0 8 * * *` means 8am UTC daily.

---

## CI/CD from GitHub (future)

The local deploy works by running `deploy.py` on your machine, which:
1. Reads credentials from `gcloud auth application-default login` (your personal GCP session)
2. Reads project config from `.env`
3. Zips `app/` from your local filesystem and uploads it

A CI/CD pipeline does the exact same thing, but runs on a GitHub Actions runner instead of your machine. The differences are:

**Authentication**: Instead of your personal `gcloud` session, GitHub Actions uses a **Workload Identity Federation** — a keyless mechanism where GitHub's OIDC token is exchanged for a short-lived GCP credential. No service account key JSON file is ever stored in GitHub.

**Secrets**: `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and the existing resource name are stored as **GitHub Actions secrets** (separate from GCP Secret Manager — these are just CI environment variables).

**What the workflow looks like** (`.github/workflows/deploy.yml`):

```yaml
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write   # required for Workload Identity Federation
      contents: read

    steps:
      - uses: actions/checkout@v4

      - uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: "projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/..."
          service_account: "football-content-agent-sa@PROJECT.iam.gserviceaccount.com"

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - run: pip install vertexai google-adk python-dotenv

      - run: python deploy.py
        env:
          GOOGLE_CLOUD_PROJECT: ${{ secrets.GOOGLE_CLOUD_PROJECT }}
          GOOGLE_CLOUD_LOCATION: ${{ secrets.GOOGLE_CLOUD_LOCATION }}
```

**Workload Identity Federation** is a GCP feature that lets external systems (GitHub, in this case) prove their identity to GCP without a long-lived key. The flow is:
1. GitHub generates a short-lived OIDC token proving "this is a run from repo X on branch main"
2. GCP exchanges that token for a short-lived GCP credential scoped to the specified service account
3. The deploy script runs with that credential — same as running with `gcloud auth application-default login` locally

To set this up you create a **Workload Identity Pool** in GCP that trusts GitHub's OIDC issuer, then grant the pool permission to impersonate `football-content-agent-sa`. That's a one-time setup via `gcloud` — roughly 5 CLI commands.

**The key architectural point**: local deploy and CI/CD deploy run the same `deploy.py`. The only difference is *how credentials are obtained* (personal gcloud session vs Workload Identity) and *where config comes from* (`.env` file vs GitHub Actions secrets).
