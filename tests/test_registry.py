import pytest
from youzi.harness.skill import Skill
from youzi.harness.registry import SkillRegistry


def _skills():
    return [
        Skill.from_seed({"skill_id": "a", "name_cn": "甲", "type": "pattern",
                         "applicable_regime": ["主升", "连板生态"], "trigger": "t",
                         "entry": "e", "exit_stop": "x", "status": "active"}),
        Skill.from_seed({"skill_id": "b", "name_cn": "乙", "type": "failure_detector",
                         "applicable_regime": ["退潮"], "trigger": "t",
                         "entry": "规避", "exit_stop": "N/A", "status": "active"}),
        Skill.from_seed({"skill_id": "c", "name_cn": "丙", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t",
                         "entry": "e", "exit_stop": "x", "status": "dormant"}),
    ]


def test_registry_rejects_duplicate_ids():
    s = _skills()
    with pytest.raises(ValueError):
        SkillRegistry.from_skills([s[0], s[0]])


def test_registry_queries():
    reg = SkillRegistry.from_skills(_skills())
    assert reg.get("b").name_cn == "乙"
    assert reg.get("zzz") is None
    assert {s.skill_id for s in reg.by_status("active")} == {"a", "b"}
    assert {s.skill_id for s in reg.by_phase("主升")} == {"a", "c"}
    assert {s.skill_id for s in reg.by_type("pattern")} == {"a", "c"}
    assert {s.skill_id for s in reg.by_ecology("连板生态")} == {"a"}
    assert len(reg) == 3
