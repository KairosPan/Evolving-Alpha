from __future__ import annotations

from youzi.harness.memory_item import Lesson


class MemoryStore:
    """记忆库 M(按 lesson_id 索引)。"""

    def __init__(self, lessons: dict[str, Lesson]) -> None:
        self._lessons = dict(lessons)          # 防御性拷贝,调用方不持有同一引用

    @classmethod
    def from_lessons(cls, lessons: list[Lesson]) -> "MemoryStore":
        index: dict[str, Lesson] = {}
        for lesson in lessons:
            if lesson.lesson_id in index:
                raise ValueError(f"重复 lesson_id: {lesson.lesson_id}")
            index[lesson.lesson_id] = lesson
        return cls(index)

    def get(self, lesson_id: str) -> Lesson | None:
        return self._lessons.get(lesson_id)

    def all(self) -> list[Lesson]:
        return list(self._lessons.values())

    def for_regime(self, phase: str) -> list[Lesson]:
        """该相位适用的教训:phase ∈ phases 或 applies_all。"""
        return [l for l in self._lessons.values() if phase in l.phases or l.applies_all]

    def for_ecology(self, ecology: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if ecology in l.ecologies]

    def by_outcome(self, outcome: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if l.outcome == outcome]

    def by_pattern(self, pattern: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if l.pattern == pattern]

    def __len__(self) -> int:
        return len(self._lessons)
