# tests/test_baselines.py
from datetime import date, datetime
from youzi.schemas.market import MarketState
from youzi.universe.stock import StockSnapshot
from youzi.universe.universe import CandidateUniverse
from youzi.eval.baselines import NoTradePolicy, HighestBoardPolicy


def _state(d=date(2024, 6, 27)):
    return MarketState(date=d, max_board_height=7, limit_up_count=3, blowup_count=1,
                       blowup_rate=0.25, limit_down_count=1, echelon=[],
                       money_effect_raw=0.0, sentiment_raw=0.0, sentiment_norm=None,
                       as_of=datetime(2024, 6, 27, 15, 0))


def _uni():
    return CandidateUniverse.from_stocks([
        StockSnapshot(code="A", name="龙", status="limit_up", boards=7),
        StockSnapshot(code="B", name="中", status="limit_up", boards=3),
        StockSnapshot(code="C", name="炸", status="blowup", boards=None),
    ])


def test_no_trade_policy():
    pkg = NoTradePolicy().decide(_state(), _uni())
    assert pkg.candidates == [] and pkg.no_trade_reason


def test_highest_board_policy_picks_top_boards():
    pkg = HighestBoardPolicy().decide(_state(), _uni())
    assert {c.code for c in pkg.candidates} == {"A"}          # 7板最高
    assert pkg.candidates[0].pattern == "highest_board"


def test_highest_board_policy_no_limit_up():
    empty = CandidateUniverse.from_stocks([
        StockSnapshot(code="C", name="炸", status="blowup")])
    pkg = HighestBoardPolicy().decide(_state(), empty)
    assert pkg.candidates == [] and pkg.no_trade_reason


def test_highest_board_policy_ties_pick_all():
    u = CandidateUniverse.from_stocks([
        StockSnapshot(code="A", name="甲", status="limit_up", boards=5),
        StockSnapshot(code="B", name="乙", status="limit_up", boards=5),
        StockSnapshot(code="C", name="丙", status="limit_up", boards=2)])
    pkg = HighestBoardPolicy().decide(_state(), u)
    assert {c.code for c in pkg.candidates} == {"A", "B"}
