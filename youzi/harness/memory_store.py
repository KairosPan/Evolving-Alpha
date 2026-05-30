from __future__ import annotations

from youzi.harness.memory_item import Lesson


class MemoryStore:
    """记忆库 M(按 lesson_id 索引)。Phase-0b-1 只读/查询;process_memory CRUD 见 Phase-0b-2。"""

    def __init__(self, lessons: dict[str, Lesson]) -> None:
        self._lessons = lessons

    @classmethod
    def from_lessons(cls, lessons: list[Lesson]) -> "MemoryStore":
        index: dict[str, Lesson] = {}
        for l in lessons:
            if l.lesson_id in index:
                raise ValueError(f"重复 lesson_id: {l.lesson_id}")
            index[l.lesson_id] = l
        return cls(index)

    def get(self, lesson_id: str) -> Lesson | None:
        return self._lessons.get(lesson_id)

    def all(self) -> list[Lesson]:
        return list(self._lessons.values())

    def by_regime(self, regime: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if l.regime == regime]

    def by_outcome(self, outcome: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if l.outcome == outcome]

    def by_pattern(self, pattern: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if l.pattern == pattern]

    def __len__(self) -> int:
        return len(self._lessons)
