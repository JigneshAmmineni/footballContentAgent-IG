from pydantic import BaseModel


class FinalPost(BaseModel):
    idea_id: str
    image_path: str  # out/YYYY-MM-DD/{idea_id}/image.png
    caption: str  # revised caption + hashtags, ready to post
    priority: int  # carried from ApprovedIdea


class FinalPostList(BaseModel):
    posts: list[FinalPost]
