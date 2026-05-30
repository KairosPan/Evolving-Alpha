from youzi.harness.skill import Skill
from youzi.harness.registry import SkillRegistry
from youzi.harness.memory_store import MemoryStore
from youzi.harness.doctrine import Doctrine
from youzi.harness.cycle import StateMachine
from youzi.harness.harness import HarnessState
from youzi.harness.edit_log import EditLog
from youzi.harness.snapshot import SnapshotStore


def _h():
    skills = SkillRegistry.from_skills([
        Skill.from_seed({"skill_id": "a", "name_cn": "甲", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "active"})])
    return HarnessState(doctrine=Doctrine(), skills=skills,
                        memory=MemoryStore.from_lessons([]),
                        cycle=StateMachine())


def test_snapshot_save_list_load(tmp_path):
    store = SnapshotStore(tmp_path)
    assert store.list_versions() == [] and store.latest() is None
    log = EditLog()
    log.append("write_skill", "skill", "a", "create")
    v0 = store.save(_h(), log, label="初始")
    v1 = store.save(_h(), EditLog(), label="次版")
    assert v0 == 0 and v1 == 1
    assert store.list_versions() == [0, 1] and store.latest() == 1

    h, lg = store.load(0)
    assert h.skills.get("a").name_cn == "甲"
    assert len(lg) == 1 and lg.records()[0].tool == "write_skill"


def test_snapshot_load_missing_raises(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        SnapshotStore(tmp_path).load(99)
