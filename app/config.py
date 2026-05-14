import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root when the agent starts (local dev; no-op in Agent Engine)
load_dotenv(Path(__file__).parent.parent / ".env")

_GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "")
# Set to "1" only in the Agent Engine deployment config — never locally.
_ON_AGENT_ENGINE = os.getenv("AGENT_ENGINE", "") == "1"


def _get_secret(name: str) -> str:
    """Fetch a secret from Secret Manager when running on Agent Engine.

    Falls back to os.getenv for local dev.
    """
    val = os.getenv(name, "")
    if val:
        return val
    if not _ON_AGENT_ENGINE:
        return ""
    from google.cloud import secretmanager  # noqa: PLC0415
    client = secretmanager.SecretManagerServiceClient()
    secret_path = f"projects/{_GCP_PROJECT}/secrets/{name}/versions/latest"
    response = client.access_secret_version(name=secret_path)
    return response.payload.data.decode("utf-8").strip()


@dataclass
class ModelConfig:
    # Verify IDs at runtime:
    # python -c "from google import genai; c = genai.Client(); [print(m.name) for m in c.models.list()]"
    news_ingest: str = "gemini-2.5-flash"
    idea_judge: str = "gemini-2.5-pro"
    idea_ranker: str = "gemini-2.5-pro"
    content_planner: str = "gemini-2.5-pro"
    image_generator: str = "gpt-image-2"
    caption_writer: str = "gemini-2.5-flash"
    caption_critic: str = "gemini-2.5-flash"


@dataclass
class RssFeedConfig:
    name: str
    url: str


_DEFAULT_RSS_FEEDS = [
    RssFeedConfig("bbc_sport", "https://feeds.bbci.co.uk/sport/football/rss.xml"),
    RssFeedConfig("sky_sports", "https://www.skysports.com/rss/12040"),
    RssFeedConfig("guardian", "https://www.theguardian.com/football/rss"),
    RssFeedConfig("espn", "https://www.espn.com/espn/rss/soccer/news"),
    RssFeedConfig("90min", "https://www.90min.com/feed"),
]

_BIG5_COMPETITIONS = ["PL", "PD", "BL1", "SA", "FL1"]


@dataclass
class Config:
    models: ModelConfig = field(default_factory=ModelConfig)
    rss_feeds: list[RssFeedConfig] = field(default_factory=lambda: list(_DEFAULT_RSS_FEEDS))
    competitions: list[str] = field(default_factory=lambda: list(_BIG5_COMPETITIONS))

    # Paths — prompts and assets live inside app/ so they're bundled with Agent Engine.
    # Data and out live at project root (local dev; swap to GCS in production).
    _pkg_root: Path = field(default_factory=lambda: Path(__file__).parent)
    _project_root: Path = field(default_factory=lambda: Path(__file__).parent.parent)

    @property
    def prompt_dir(self) -> Path:
        return self._pkg_root / "prompts"

    @property
    def assets_dir(self) -> Path:
        return self._pkg_root / "assets"

    @property
    def data_dir(self) -> Path:
        return self._project_root / "data"

    @property
    def output_dir(self) -> Path:
        # Agent Engine containers only have /tmp as a writable path.
        return Path("/tmp/out") if _ON_AGENT_ENGINE else self._project_root / "out"

    @property
    def badges_dir(self) -> Path:
        return self._project_root / "data" / "badges"

    @property
    def seen_file(self) -> Path:
        return self._project_root / "data" / "seen.json"

    @property
    def archive_dir(self) -> Path:
        return self._project_root / "data" / "archive"

    def load_prompt(self, name: str) -> str:
        return (self.prompt_dir / f"{name}.md").read_text(encoding="utf-8")

    def football_data_token(self) -> str:
        token = _get_secret("FOOTBALL_DATA_TOKEN")
        if not token:
            raise EnvironmentError("FOOTBALL_DATA_TOKEN not set")
        return token

    def openai_api_key(self) -> str:
        key = _get_secret("OPENAI_API_KEY")
        if not key:
            raise EnvironmentError("OPENAI_API_KEY not set")
        return key

    def news_api_key(self) -> str:
        key = _get_secret("NEWS_API_KEY")
        if not key:
            raise EnvironmentError("NEWS_API_KEY not set")
        return key

    def gcs_bucket_name(self) -> str:
        val = _get_secret("GCS_BUCKET_NAME")
        if not val:
            raise EnvironmentError("GCS_BUCKET_NAME not set")
        return val

    def instagram_user_id(self) -> str:
        val = _get_secret("INSTAGRAM_USER_ID")
        if not val:
            raise EnvironmentError("INSTAGRAM_USER_ID not set")
        return val

    def instagram_access_token(self) -> str:
        val = _get_secret("INSTAGRAM_ACCESS_TOKEN")
        if not val:
            raise EnvironmentError("INSTAGRAM_ACCESS_TOKEN not set")
        return val


# Module-level singleton — imported by all agents and tools
config = Config()
