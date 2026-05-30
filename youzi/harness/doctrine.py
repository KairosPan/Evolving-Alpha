from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from youzi.harness.regime import parse_regime_field


class DoctrineEntry(BaseModel):
    """p doctrine 条目(可变;immutable=True 为纪律红线,写保护在 rewrite/remove 强制)。"""
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    section: str
    regime_raw: str = ""
    phases: list[str] = Field(default_factory=list)
    ecologies: list[str] = Field(default_factory=list)
    applies_all: bool = False
    immutable: bool = False
    guidance: str
    source_lines: list[int] = Field(default_factory=list)

    @classmethod
    def from_seed(cls, d: dict) -> "DoctrineEntry":
        raw = d.get("regime", "")
        phases, ecologies, applies_all = parse_regime_field(raw)
        rest = {k: v for k, v in d.items() if k != "regime"}
        return cls(**rest, regime_raw=raw, phases=phases,
                   ecologies=ecologies, applies_all=applies_all)


class Doctrine(BaseModel):
    """doctrine 容器。"""
    entries: list[DoctrineEntry] = Field(default_factory=list)

    def for_regime(self, phase: str) -> list[DoctrineEntry]:
        """某相位适用的 doctrine:phase ∈ phases 或 applies_all。原序返回。"""
        return [e for e in self.entries if phase in e.phases or e.applies_all]

    def for_ecology(self, ecology: str) -> list[DoctrineEntry]:
        return [e for e in self.entries if ecology in e.ecologies]

    def immutable_core(self) -> list[DoctrineEntry]:
        return [e for e in self.entries if e.immutable]

    def mutable_entries(self) -> list[DoctrineEntry]:
        return [e for e in self.entries if not e.immutable]

    @classmethod
    def from_seed_list(cls, items: list[dict]) -> "Doctrine":
        return cls(entries=[DoctrineEntry.from_seed(d) for d in items])
