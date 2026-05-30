from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from youzi.harness.regime import classify_regime

Outcome = Literal["win", "loss", "principle"]


class Importance(BaseModel):
    """记忆重要度(可变)。weight = base × time_decay × regime_decay(双衰减,蓝图 §8)。"""
    base: float = 1.0
    time_decay: float = 1.0
    regime_decay: float = 1.0

    def weight(self) -> float:
        return self.base * self.time_decay * self.regime_decay

    def demote(self, factor: float) -> None:
        """按 factor 压低 time_decay(越过的区域降权,不删)。"""
        if not 0.0 < factor <= 1.0:
            raise ValueError(f"demote factor 必须在 (0,1], got {factor}")
        self.time_decay *= factor


def _norm_regime(raw: str) -> str:
    """记忆的 regime:'all' 原样保留;否则归一到 canonical 相位,归一失败则原样保留。"""
    s = (raw or "").strip()
    if s == "all":
        return "all"
    kind, value = classify_regime(s)
    return value if kind == "phase" else s


class Lesson(BaseModel):
    """M 记忆条目(可变)。"""
    model_config = ConfigDict(extra="forbid")
    lesson_id: str
    regime: str
    pattern: str = ""
    outcome: Outcome
    failure_signature: str = ""
    named_analog: str = ""
    lesson: str
    source_lines: list[int] = Field(default_factory=list)
    importance: Importance = Field(default_factory=Importance)

    @classmethod
    def from_seed(cls, d: dict) -> "Lesson":
        return cls(**{**d, "regime": _norm_regime(d.get("regime", ""))})
