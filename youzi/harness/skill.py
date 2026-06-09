from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from youzi.harness.regime import split_regimes

SkillType = Literal["pattern", "feature", "failure_detector"]
SkillStatus = Literal["active", "incubating", "dormant", "retired"]


class SkillStats(BaseModel):
    """技能滚动绩效(可变, 运行期更新)。EWMA 胜率为 time-decay 雏形,后续接 regime 双衰减。"""
    n: int = 0
    wins: int = 0
    losses: int = 0
    nukes: int = 0           # 被砸(nuked)次数;nuke_rate = nukes/n。由 apply_credit 维护
    ewma_winrate: float | None = None
    pnl_ratio: float | None = None
    expectancy: float | None = None      # 语义=advantage(score−当日池基线)累计均值,去市场β;由 apply_credit Welford 维护
    expectancy_raw: float | None = None  # 原始 score 口径累计均值(第二字段,保留旧口径可溯;同上维护)
    oracle_gap: float | None = None

    def record(self, win: bool, decay: float = 0.1) -> None:
        """记一次结果。首样本直接置入 ewma;之后 ewma = decay*x + (1-decay)*ewma。"""
        if not 0.0 < decay <= 1.0:
            raise ValueError(f"decay 必须在 (0,1], got {decay}")
        x = 1.0 if win else 0.0
        self.n += 1
        self.wins += int(win)
        self.losses += int(not win)
        self.ewma_winrate = x if self.ewma_winrate is None else decay * x + (1 - decay) * self.ewma_winrate


class Skill(BaseModel):
    """K 技能(可变 harness 状态;Refiner 后续编辑)。"""
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    skill_id: str
    name_cn: str
    type: SkillType
    applicable_regime: list[str] = Field(default_factory=list)   # 原始(可溯源)
    phases: list[str] = Field(default_factory=list)              # 归一 canonical 相位
    ecologies: list[str] = Field(default_factory=list)           # 归一生态标签
    applies_all: bool = False             # applicable_regime 含 "all" → 对任意"相位"通用(by_phase 认);不影响 by_ecology
    trigger: str
    entry: str
    exit_stop: str
    taboo: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    source_lines: list[int] = Field(default_factory=list)
    status: SkillStatus = "incubating"
    notes: str = ""
    stats: SkillStats = Field(default_factory=SkillStats)

    @classmethod
    def from_seed(cls, d: dict) -> "Skill":
        raw = d.get("applicable_regime", [])
        applies_all = "all" in raw
        phases, ecologies = split_regimes([r for r in raw if r != "all"])
        return cls(**{**d, "phases": phases, "ecologies": ecologies,
                      "applies_all": applies_all})
