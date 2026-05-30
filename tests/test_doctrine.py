# tests/test_doctrine.py  (整体替换)
from youzi.harness.doctrine import DoctrineEntry, Doctrine


def _entries():
    return [
        DoctrineEntry.from_seed({"section": "退潮作战", "regime": "退潮",
                                 "immutable": False, "guidance": "降题材预期"}),
        DoctrineEntry.from_seed({"section": "纪律红线:退潮不接力", "regime": "all",
                                 "immutable": True, "guidance": "退潮期禁止接力"}),
        DoctrineEntry.from_seed({"section": "主升作战", "regime": "主升/震荡补涨",
                                 "immutable": False, "guidance": "持有龙头"}),
    ]


def test_from_seed_parses_multi_regime():
    e = _entries()[2]
    assert e.phases == ["主升", "震荡补涨"]
    assert e.regime_raw == "主升/震荡补涨"


def test_doctrine_for_regime_membership_and_all():
    doc = Doctrine(entries=_entries())
    assert [e.section for e in doc.for_regime("退潮")] == ["退潮作战", "纪律红线:退潮不接力"]
    # 主升作战 适用于 主升 与 震荡补涨 两相位; all 永远命中
    assert [e.section for e in doc.for_regime("震荡补涨")] == ["纪律红线:退潮不接力", "主升作战"]
    assert "纪律红线:退潮不接力" in [e.section for e in doc.for_regime("主升")]
    assert [e.section for e in doc.immutable_core()] == ["纪律红线:退潮不接力"]
    assert len(doc.mutable_entries()) == 2


def test_doctrine_entry_forbids_unknown_keys():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        DoctrineEntry.from_seed({"section": "x", "regime": "all", "immutable": False,
                                 "guidance": "g", "typo_key": 1})
