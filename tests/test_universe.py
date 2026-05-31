from youzi.universe.stock import StockSnapshot
from youzi.universe.universe import CandidateUniverse


def _stocks():
    return [
        StockSnapshot(code="1", name="龙", status="limit_up", boards=7, industry="芯片"),
        StockSnapshot(code="2", name="中", status="limit_up", boards=3, industry="芯片"),
        StockSnapshot(code="3", name="炸", status="blowup", boards=0, industry="军工"),
        StockSnapshot(code="4", name="跌", status="limit_down", boards=0, industry="军工"),
    ]


def test_universe_queries():
    u = CandidateUniverse.from_stocks(_stocks())
    assert u.get("1").name == "龙" and u.get("zzz") is None
    assert {s.code for s in u.by_status("limit_up")} == {"1", "2"}
    assert {s.code for s in u.by_min_boards(3)} == {"1", "2"}       # 连板>=3
    assert {s.code for s in u.by_min_boards(7)} == {"1"}
    assert {s.code for s in u.by_industry("芯片")} == {"1", "2"}
    assert len(u) == 4


def test_universe_rejects_duplicate_code():
    import pytest
    with pytest.raises(ValueError):
        CandidateUniverse.from_stocks([_stocks()[0], _stocks()[0]])


def test_empty_universe_is_truthy():
    u = CandidateUniverse.from_stocks([])
    assert bool(u) is True and len(u) == 0          # 杀 falsy-trap(0b-3 教训)
