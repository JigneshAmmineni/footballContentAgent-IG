import json
import os
from difflib import SequenceMatcher
from pathlib import Path

from app.models.raw_idea import RawIdea

_SEMANTIC_THRESHOLD = 0.82  # string similarity above this = near-duplicate
_GCS_SEEN_BLOB = "dedup/seen.json"


def dedup(ideas: list[RawIdea], seen_path: Path) -> list[RawIdea]:
    """Remove previously-seen ideas and cross-source semantic near-duplicates.

    Writes newly-approved IDs to seen_path (local) or GCS (Agent Engine).
    """
    seen_ids = _load_seen(seen_path)
    fresh = [i for i in ideas if i.id not in seen_ids]
    unique = _semantic_dedup(fresh)
    _save_seen(seen_path, seen_ids | {i.id for i in unique})
    return unique


def _use_gcs() -> bool:
    return os.getenv("AGENT_ENGINE", "") == "1"


def _load_seen(path: Path) -> set[str]:
    if _use_gcs():
        return _load_seen_gcs()
    if path.exists():
        try:
            return set(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValueError):
            return set()
    return set()


def _save_seen(path: Path, ids: set[str]) -> None:
    if _use_gcs():
        _save_seen_gcs(ids)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(ids), indent=2), encoding="utf-8")


def _load_seen_gcs() -> set[str]:
    from google.cloud import storage  # noqa: PLC0415
    from app.config import config  # noqa: PLC0415
    client = storage.Client()
    blob = client.bucket(config.gcs_bucket_name()).blob(_GCS_SEEN_BLOB)
    if not blob.exists():
        return set()
    try:
        return set(json.loads(blob.download_as_text()))
    except (json.JSONDecodeError, ValueError):
        return set()


def _save_seen_gcs(ids: set[str]) -> None:
    from google.cloud import storage  # noqa: PLC0415
    from app.config import config  # noqa: PLC0415
    client = storage.Client()
    blob = client.bucket(config.gcs_bucket_name()).blob(_GCS_SEEN_BLOB)
    blob.upload_from_string(
        json.dumps(sorted(ids), indent=2),
        content_type="application/json",
    )


def _semantic_dedup(ideas: list[RawIdea]) -> list[RawIdea]:
    """Collapse ideas whose content_hint is highly similar (cross-source duplicates)."""
    unique: list[RawIdea] = []
    for candidate in ideas:
        if not _is_near_duplicate(candidate, unique):
            unique.append(candidate)
    return unique


def _is_near_duplicate(candidate: RawIdea, existing: list[RawIdea]) -> bool:
    for seen in existing:
        ratio = SequenceMatcher(
            None,
            candidate.content_hint.lower(),
            seen.content_hint.lower(),
        ).ratio()
        if ratio >= _SEMANTIC_THRESHOLD:
            return True
    return False
