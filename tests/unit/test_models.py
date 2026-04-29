from datetime import datetime
from app.models.raw_idea import RawIdea, RawIdeaList
from app.models.approved_idea import ApprovedIdea, ApprovedIdeaList
from app.models.final_post import FinalPost, FinalPostList


def test_raw_idea_roundtrip():
    idea = RawIdea(
        id="abc123",
        source="football_data",
        content_hint="Arsenal 2–1 Chelsea (PL)",
        raw_data={"match_id": 1},
        suggested_type="match_result",
        source_url="https://example.com/article",
    )
    data = idea.model_dump(mode="json")
    restored = RawIdea(**data)
    assert restored.id == idea.id
    assert restored.source == idea.source
    assert restored.source_url == idea.source_url


def test_approved_idea_priority_bounds():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ApprovedIdea(raw_idea_id="x", priority=0, content_direction="test")
    with pytest.raises(ValidationError):
        ApprovedIdea(raw_idea_id="x", priority=11, content_direction="test")
    idea = ApprovedIdea(raw_idea_id="x", priority=5, content_direction="test")
    assert idea.priority == 5


def test_approved_idea_list_roundtrip():
    payload = {
        "ideas": [
            {"raw_idea_id": "a", "priority": 7, "content_direction": "Some direction"},
            {"raw_idea_id": "b", "priority": 3, "content_direction": "Another direction", "data_needed": ["extra"]},
        ]
    }
    result = ApprovedIdeaList(**payload)
    assert len(result.ideas) == 2
    dumped = result.model_dump(mode="json")
    restored = ApprovedIdeaList(**dumped)
    assert restored.ideas[0].raw_idea_id == "a"


def test_final_post_roundtrip():
    post = FinalPost(
        idea_id="abc",
        image_path="out/2026-04-27/abc/image.png",
        caption="Great goal! 🔥\n\n#PremierLeague",
        priority=8,
    )
    data = post.model_dump(mode="json")
    restored = FinalPost(**data)
    assert restored.idea_id == post.idea_id
    assert restored.caption == post.caption
