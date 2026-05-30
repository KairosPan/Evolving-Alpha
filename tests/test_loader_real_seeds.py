# tests/test_loader_real_seeds.py
from pathlib import Path
from youzi.harness.loader import load_seeds
from youzi.harness.harness import HarnessState
from youzi.harness.regime import CANONICAL_PHASES

SEEDS = Path(__file__).resolve().parent.parent / "seeds"


def test_load_real_seeds_counts_and_validity():
    h = load_seeds(SEEDS)
    assert isinstance(h, HarnessState)
    # 计数与提交的 v1 种子一致(变更种子需同步改这里)
    assert len(h.skills) == 57
    assert len(h.memory) == 21
    assert len(h.doctrine.entries) == 22
    assert len(h.cycle.phases) == 7


def test_loaded_skill_phases_are_canonical_or_empty():
    h = load_seeds(SEEDS)
    allowed = set(CANONICAL_PHASES)
    for s in h.skills.all():
        # 归一后的 phases 必须全是 canonical(或空), 不得残留变体/触发条件
        assert set(s.phases) <= allowed, f"{s.skill_id} 残留非 canonical 相位: {s.phases}"


def test_loaded_doctrine_has_immutable_core():
    h = load_seeds(SEEDS)
    core = h.doctrine.immutable_core()
    assert len(core) >= 8                       # v1 有 10 条纪律红线
    assert all(e.immutable for e in core)


def test_loader_missing_dir_raises():
    import pytest
    with pytest.raises(FileNotFoundError):
        load_seeds(SEEDS / "does_not_exist")
