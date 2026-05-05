from pydantic import BaseModel
from app.models.overlay_spec import OverlaySpec


class FinalPost(BaseModel):
    idea_id: str
    image_path: str       # out/YYYY-MM-DD/{idea_id}/image.png
    caption: str          # Instagram caption + hashtags, ready to post
    priority: int         # carried from ApprovedIdea
    overlay_spec: OverlaySpec  # the overlay that was rendered onto the image


class FinalPostList(BaseModel):
    posts: list[FinalPost]
