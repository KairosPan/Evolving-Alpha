"""Pydantic schemas for LLM structured output."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ThemeOut(BaseModel):
    name: str
    members: list[str]
    leader: Optional[str] = None
    phase: Literal["budding", "horizontal", "vertical", "switching", "exhausted"]
    catalysts: list[str] = Field(default_factory=list)
    resonance_score: float = Field(ge=0, le=1)


class ThemeAnalystOut(BaseModel):
    themes: list[ThemeOut]
    main_theme: Optional[str] = None
    theme_axis: Literal["horizontal", "vertical", "switching", "exhausted"]


class PatternEdgeOut(BaseModel):
    emotion_phase: Literal[
        "chaos", "recovery", "warming", "main_rise",
        "climax", "divergence", "decay_1", "decay_mid", "decay_2",
    ]
    confidence: float = Field(ge=0, le=1)
    reason: str
