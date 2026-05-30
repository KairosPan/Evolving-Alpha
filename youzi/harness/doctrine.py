from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from youzi.harness.regime import classify_regime


def _norm(raw: str) -> str:
    s = (raw or "").strip()
    if s == "all":
        return "all"
    kind, value = classify_regime(s)
    return value if kind == "phase" else s


class DoctrineEntry(BaseModel):
    """p doctrine 条目(可变;但 immutable=True 的为纪律红线,写保护在 Phase-0b-2 强制)。"""
    model_config = ConfigDict(extra="forbid")

    section: str
    regime: str
    immutable: bool = False
    guidance: str
    source_lines: list[int] = Field(default_factory=list)

    @classmethod
    def from_seed(cls, d: dict) -> "DoctrineEntry":
        return cls(**{**d, "regime": _norm(d.get("regime", ""))})


class Doctrine(BaseModel):
    """doctrine 容器。"""
    entries: list[DoctrineEntry] = Field(default_factory=list)

    def for_regime(self, phase: str) -> list[DoctrineEntry]:
        """某相位适用的 doctrine:匹配该相位的 + regime=='all' 的。原序返回。"""
        return [e for e in self.entries if e.regime == phase or e.regime == "all"]

    def immutable_core(self) -> list[DoctrineEntry]:
        return [e for e in self.entries if e.immutable]

    def mutable_entries(self) -> list[DoctrineEntry]:
        return [e for e in self.entries if not e.immutable]

    @classmethod
    def from_seed_list(cls, items: list[dict]) -> "Doctrine":
        return cls(entries=[DoctrineEntry.from_seed(d) for d in items])
