from youzi.harness.memory_item import Lesson
from youzi.harness.memory_store import MemoryStore


def _lessons():
    return [
        Lesson.from_seed({"lesson_id": "l1", "regime": "退潮", "pattern": "接力",
                          "outcome": "principle", "lesson": "退潮不接力"}),
        Lesson.from_seed({"lesson_id": "l2", "regime": "退潮", "pattern": "高位",
                          "outcome": "loss", "named_analog": "神马电力2024/6/28",
                          "lesson": "由强转弱即退潮拐点"}),
        Lesson.from_seed({"lesson_id": "l3", "regime": "all", "pattern": "纪律",
                          "outcome": "principle", "lesson": "计划交易不上头"}),
    ]


def test_memory_store_queries():
    store = MemoryStore.from_lessons(_lessons())
    assert store.get("l2").named_analog == "神马电力2024/6/28"
    assert {l.lesson_id for l in store.by_regime("退潮")} == {"l1", "l2"}
    assert {l.lesson_id for l in store.by_outcome("principle")} == {"l1", "l3"}
    assert {l.lesson_id for l in store.by_pattern("纪律")} == {"l3"}
    assert len(store) == 3
