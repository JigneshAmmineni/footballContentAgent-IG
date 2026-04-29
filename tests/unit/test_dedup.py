import json
import tempfile
from pathlib import Path

from app.models.raw_idea import RawIdea
from app.tools.dedup import dedup, _load_seen, _save_seen, _semantic_dedup


def _make_idea(id: str, hint: str, source: str = "test") -> RawIdea:
    return RawIdea(id=id, source=source, content_hint=hint, raw_data={})


def test_seen_file_roundtrip(tmp_path):
    path = tmp_path / "seen.json"
    ids = {"abc", "def", "ghi"}
    _save_seen(path, ids)
    loaded = _load_seen(path)
    assert loaded == ids


def test_dedup_removes_seen(tmp_path):
    seen_path = tmp_path / "seen.json"
    _save_seen(seen_path, {"id1", "id2"})
    ideas = [
        _make_idea("id1", "Arsenal beat Chelsea"),
        _make_idea("id2", "Haaland scores hat-trick"),
        _make_idea("id3", "New transfer news"),
    ]
    result = dedup(ideas, seen_path)
    assert len(result) == 1
    assert result[0].id == "id3"


def test_dedup_writes_new_ids(tmp_path):
    seen_path = tmp_path / "seen.json"
    ideas = [_make_idea("x1", "Some headline"), _make_idea("x2", "Another headline")]
    dedup(ideas, seen_path)
    saved = _load_seen(seen_path)
    assert "x1" in saved and "x2" in saved


def test_dedup_idempotent(tmp_path):
    seen_path = tmp_path / "seen.json"
    ideas = [_make_idea("a", "Match result"), _make_idea("b", "Transfer news")]
    first = dedup(ideas, seen_path)
    second = dedup(ideas, seen_path)
    assert len(first) == 2
    assert len(second) == 0  # all seen on second run


def test_semantic_dedup_collapses_near_duplicates():
    ideas = [
        _make_idea("1", "Haaland scores hat-trick against Arsenal in Premier League"),
        _make_idea("2", "Haaland scores hat trick against Arsenal in Premier League"),  # near-identical
        _make_idea("3", "Vinicius Jr wins Player of the Month award"),
    ]
    result = _semantic_dedup(ideas)
    assert len(result) == 2  # near-duplicate collapsed


def test_semantic_dedup_keeps_distinct():
    ideas = [
        _make_idea("1", "Haaland scores hat-trick"),
        _make_idea("2", "Bellingham injured for three weeks"),
        _make_idea("3", "Barcelona sign new midfielder"),
    ]
    result = _semantic_dedup(ideas)
    assert len(result) == 3
