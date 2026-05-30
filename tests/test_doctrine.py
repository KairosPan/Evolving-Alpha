from youzi.harness.doctrine import DoctrineEntry, Doctrine


def _entries():
    return [
        DoctrineEntry.from_seed({"section": "退潮作战", "regime": "退潮期",
                                 "immutable": False, "guidance": "降题材预期"}),
        DoctrineEntry.from_seed({"section": "纪律红线:退潮不接力", "regime": "all",
                                 "immutable": True, "guidance": "退潮期禁止接力"}),
        DoctrineEntry.from_seed({"section": "主升作战", "regime": "主升",
                                 "immutable": False, "guidance": "持有龙头"}),
    ]


def test_from_seed_normalizes_regime():
    e = _entries()[0]
    assert e.regime == "退潮"          # 归一


def test_doctrine_queries():
    doc = Doctrine(entries=_entries())
    assert [e.section for e in doc.for_regime("退潮")] == ["退潮作战", "纪律红线:退潮不接力"]
    # all 适用于任何相位
    assert "纪律红线:退潮不接力" in [e.section for e in doc.for_regime("主升")]
    assert [e.section for e in doc.immutable_core()] == ["纪律红线:退潮不接力"]
    assert len(doc.mutable_entries()) == 2


def test_doctrine_entry_forbids_unknown_keys():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        DoctrineEntry.from_seed({"section": "x", "regime": "all", "immutable": False,
                                 "guidance": "g", "typo_key": 1})
