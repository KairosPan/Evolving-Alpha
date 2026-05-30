from __future__ import annotations

from dataclasses import dataclass

from youzi.harness.cycle import StateMachine
from youzi.harness.doctrine import Doctrine
from youzi.harness.memory_store import MemoryStore
from youzi.harness.registry import SkillRegistry
from youzi.harness.skill import Skill


@dataclass
class HarnessState:
    """Harness 状态 H=(p,K,M)+情绪周期状态机。Phase-0b-1 为只读载入态;编辑/版本化见 0b-2。

    G(子 Agent)留待 Phase-1(LLM 驱动模块),此处暂不建模。
    """
    doctrine: Doctrine          # p
    skills: SkillRegistry       # K
    memory: MemoryStore         # M
    cycle: StateMachine         # G_cycle 种子

    def active_skills_for(self, phase: str) -> list[Skill]:
        """该相位下当前可用(active)的技能。"""
        return [s for s in self.skills.by_phase(phase) if s.status == "active"]
