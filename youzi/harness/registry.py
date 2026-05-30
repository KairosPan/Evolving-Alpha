from __future__ import annotations

from youzi.harness.skill import Skill


class SkillRegistry:
    """技能库 K(按 id 索引)。Phase-0b-1 只读/查询;CRUD 编辑见 Phase-0b-2。"""

    def __init__(self, skills: dict[str, Skill]) -> None:
        self._skills = skills

    @classmethod
    def from_skills(cls, skills: list[Skill]) -> "SkillRegistry":
        index: dict[str, Skill] = {}
        for s in skills:
            if s.skill_id in index:
                raise ValueError(f"重复 skill_id: {s.skill_id}")
            index[s.skill_id] = s
        return cls(index)

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def by_status(self, status: str) -> list[Skill]:
        return [s for s in self._skills.values() if s.status == status]

    def by_type(self, type_: str) -> list[Skill]:
        return [s for s in self._skills.values() if s.type == type_]

    def by_phase(self, phase: str) -> list[Skill]:
        return [s for s in self._skills.values() if phase in s.phases]

    def by_ecology(self, ecology: str) -> list[Skill]:
        return [s for s in self._skills.values() if ecology in s.ecologies]

    def __len__(self) -> int:
        return len(self._skills)
