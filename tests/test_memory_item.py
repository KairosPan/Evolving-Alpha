from youzi.harness.memory_item import Lesson, Importance


def test_importance_weight_and_demote():
    imp = Importance(base=0.8, time_decay=1.0, regime_decay=1.0)
    assert abs(imp.weight() - 0.8) < 1e-9
    imp.demote(0.5)                       # 同时打到 time_decay
    assert abs(imp.time_decay - 0.5) < 1e-9
    assert abs(imp.weight() - 0.4) < 1e-9


def test_lesson_from_seed_normalizes_regime_keeps_all():
    s = Lesson.from_seed({
        "lesson_id": "no_relay_in_ebb", "regime": "退潮期", "outcome": "principle",
        "lesson": "退潮不接力", "source_lines": [1272],
    })
    assert s.regime == "退潮"             # 归一
    assert s.outcome == "principle"
    s2 = Lesson.from_seed({
        "lesson_id": "disc", "regime": "all", "outcome": "principle",
        "lesson": "计划交易不上头",
    })
    assert s2.regime == "all"             # all 保留不归一


def test_lesson_loss_with_analog():
    s = Lesson.from_seed({
        "lesson_id": "shenma_ebb", "regime": "退潮", "outcome": "loss",
        "failure_signature": "最高连板率先走弱断板大阴", "named_analog": "神马电力2024/6/28",
        "lesson": "由强转弱即退潮拐点, 回避高位", "source_lines": [437, 438],
    })
    assert s.named_analog == "神马电力2024/6/28" and s.outcome == "loss"


def test_importance_demote_rejects_bad_factor():
    import pytest
    imp = Importance()
    with pytest.raises(ValueError):
        imp.demote(0.0)
    with pytest.raises(ValueError):
        imp.demote(1.5)
