from __future__ import annotations

from youzi.harness.memory_item import Lesson


class MemoryStore:
    """记忆库 M(按 lesson_id 索引)。Phase-0b-1 只读/查询;process_memory CRUD 见 Phase-0b-2。"""

    def __init__(self, lessons: dict[str, Lesson]) -> None:
        self._lessons = lessons

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

    def by_regime(self, regime: str) -> list[Lesson]:
        return [lesson for lesson in self._lessons.values() if lesson.regime == regime]

    def for_regime(self, phase: str) -> list[Lesson]:
        """该相位适用的教训:regime==phase 的 + regime=='all' 的通用原则。"""
        return [lesson for lesson in self._lessons.values()
                if lesson.regime == phase or lesson.regime == "all"]

    def by_outcome(self, outcome: str) -> list[Lesson]:
        return [lesson for lesson in self._lessons.values() if lesson.outcome == outcome]

    def by_pattern(self, pattern: str) -> list[Lesson]:
        return [lesson for lesson in self._lessons.values() if lesson.pattern == pattern]

    def __len__(self) -> int:
        return len(self._lessons)
