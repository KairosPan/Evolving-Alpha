# youzi_web/data_access.py
from __future__ import annotations

from pathlib import Path

from youzi.harness.harness import HarnessState
from youzi.harness.loader import load_seeds
from youzi.harness.snapshot import SnapshotStore

SEEDS_DIR = Path(__file__).resolve().parent.parent / "seeds"


def harness_view(h: HarnessState) -> dict:
    """领域 H → 视图 dict;补算 Skill 没有的 hit_rate/nuke_rate(=wins/n、nukes/n;n=0→None)。"""
    d = h.to_dict()
    for s in d["skills"]:
        st = s["stats"]
        n = st["n"]
        st["hit_rate"] = (st["wins"] / n) if n else None
        st["nuke_rate"] = (st["nukes"] / n) if n else None
    return d


def seed_harness() -> HarnessState:
    return load_seeds(SEEDS_DIR)


def snapshot_harness(store: SnapshotStore, version: int) -> HarnessState:
    h, _ = store.load(version)
    return h
