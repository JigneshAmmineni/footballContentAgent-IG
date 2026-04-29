from pydantic import BaseModel, Field


class ApprovedIdea(BaseModel):
    raw_idea_id: str
    priority: int = Field(ge=1, le=10)  # 1 = lowest, 10 = highest
    content_direction: str  # free-form editorial brief for the content generator
    data_needed: list[str] = []  # additional fetches the content generator will need
    source_url: str | None = None  # carried from RawIdea for image sourcing


class ApprovedIdeaList(BaseModel):
    ideas: list[ApprovedIdea]
