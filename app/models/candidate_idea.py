from pydantic import BaseModel


class CandidateIdea(BaseModel):
    raw_idea_id: str
    content_direction: str  # editorial brief from the judge
    data_needed: list[str] = []
    source_url: str | None = None


class CandidateIdeaList(BaseModel):
    ideas: list[CandidateIdea]
