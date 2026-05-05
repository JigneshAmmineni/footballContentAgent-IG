from typing import Literal
from pydantic import BaseModel


class OverlayRow(BaseModel):
    label: str   # e.g. "24' Kvaratskhelia", "Goals", "xG"
    value: str = ""  # e.g. "", "3", "2.7" — empty for scorer rows
    side: Literal["left", "right", "center"] = "left"


class OverlaySpec(BaseModel):
    layout: Literal["score_card", "player_card", "table_card", "quote_card"]
    header: str            # e.g. "UCL Semi-Final · FT"
    left_label: str = ""   # score_card: home team; player_card: player name
    right_label: str = ""  # score_card: away team
    center_text: str = ""  # score_card: "5 - 4"; quote_card: the quote text
    rows: list[OverlayRow]
    footer: str = ""       # e.g. "May 1, 2026 · Champions League"
