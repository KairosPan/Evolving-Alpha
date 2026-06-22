from datetime import date, datetime

import pytest

from youzi.store.db import Database
from youzi.store.models import (
    AccountDaily, OpsCandidate, OpsDecision, OpsSession, OpsFill, OpsReview,
)
from youzi.store.ops_repo import OpsRepository

FIXED = datetime(2026, 6, 22, 8, 0, 0)


@pytest.fixture
def repo():
    db = Database(":memory:")
    db.migrate()
    yield OpsRepository(db, clock=lambda: FIXED)
    db.close()


def test_create_and_get_session(repo):
    s = repo.create_session(OpsSession(trade_date=date(2026, 6, 22), regime_read="主升"))
    assert s.session_id is not None
    assert s.created_at == FIXED
    got = repo.get_session(s.session_id)
    assert got.trade_date == date(2026, 6, 22)
    assert got.regime_read == "主升"


def test_session_for_date_and_list(repo):
    repo.create_session(OpsSession(trade_date=date(2026, 6, 22)))
    repo.create_session(OpsSession(trade_date=date(2026, 6, 23)))
    assert repo.session_for_date(date(2026, 6, 23)) is not None
    listed = repo.list_sessions()
    assert [s.trade_date for s in listed] == [date(2026, 6, 23), date(2026, 6, 22)]


def test_add_and_read_candidates_ordered_by_rank(repo):
    s = repo.create_session(OpsSession(trade_date=date(2026, 6, 22)))
    repo.add_candidates(s.session_id, [
        OpsCandidate(session_id=s.session_id, code="600519", rank=2, pattern="首板"),
        OpsCandidate(session_id=s.session_id, code="000001", rank=1, pattern="连板"),
    ])
    cands = repo.candidates_for(s.session_id)
    assert [c.code for c in cands] == ["000001", "600519"]
    assert cands[0].candidate_id is not None


def _session_with_candidate(repo):
    s = repo.create_session(OpsSession(trade_date=date(2026, 6, 22)))
    [c] = repo.add_candidates(s.session_id, [
        OpsCandidate(session_id=s.session_id, code="600519", rank=1, pattern="首板")])
    return s, c


def test_confirm_decision_pulls_code_from_candidate(repo):
    s, c = _session_with_candidate(repo)
    d = repo.confirm_decision(s.session_id, c.candidate_id,
                              intent_side="buy", planned_price=10.0, planned_qty=100)
    assert d.decision_id is not None
    assert d.action == "confirm" and d.code == "600519"
    assert d.intent_side == "buy" and d.status == "planned"
    assert d.created_at == FIXED


def test_skip_marks_cancelled(repo):
    s, c = _session_with_candidate(repo)
    d = repo.skip_candidate(s.session_id, c.candidate_id, note="情绪退潮")
    assert d.action == "skip" and d.status == "cancelled"


def test_manual_add_has_no_candidate(repo):
    s = repo.create_session(OpsSession(trade_date=date(2026, 6, 22)))
    d = repo.manual_add(s.session_id, "000001", intent_side="buy")
    assert d.candidate_id is None and d.code == "000001" and d.action == "manual_add"
    assert [x.decision_id for x in repo.decisions_for(s.session_id)] == [d.decision_id]


def test_buy_fill_opens_position(repo):
    s = repo.create_session(OpsSession(trade_date=date(2026, 6, 22)))
    fill, pos = repo.record_fill(OpsFill(
        code="600519", side="buy", price=10.0, qty=100,
        filled_at=datetime(2026, 6, 23, 9, 30), fee=5.0))
    assert fill.fill_id is not None and fill.position_id == pos.position_id
    assert pos.status == "open" and pos.qty_open == 100
    assert pos.opened_on == date(2026, 6, 23)
    assert repo.open_position_for("600519").position_id == pos.position_id


def test_sell_fill_realizes_pnl_and_closes(repo):
    repo.record_fill(OpsFill(code="600519", side="buy", price=10.0, qty=100,
                             filled_at=datetime(2026, 6, 23, 9, 30)))
    fill, pos = repo.record_fill(OpsFill(
        code="600519", side="sell", price=12.0, qty=100,
        filled_at=datetime(2026, 6, 24, 14, 0), fee=3.0))
    assert pos.status == "closed" and pos.qty_open == 0
    assert pos.realized_pnl == pytest.approx((12.0 - 10.0) * 100 - 3.0)
    assert pos.closed_on == date(2026, 6, 24)


def test_fill_marks_linked_decision_executed(repo):
    s = repo.create_session(OpsSession(trade_date=date(2026, 6, 22)))
    d = repo.manual_add(s.session_id, "000001", intent_side="buy")
    repo.record_fill(OpsFill(decision_id=d.decision_id, code="000001", side="buy",
                             price=8.0, qty=200, filled_at=datetime(2026, 6, 23, 9, 30)))
    assert repo.decisions_for(s.session_id)[0].status == "executed"


def test_sell_without_position_raises(repo):
    with pytest.raises(ValueError):
        repo.record_fill(OpsFill(code="600519", side="sell", price=12.0, qty=100,
                                 filled_at=datetime(2026, 6, 24, 14, 0)))


def test_review_roundtrip(repo):
    s = repo.create_session(OpsSession(trade_date=date(2026, 6, 22)))
    r = repo.add_review(OpsReview(session_id=s.session_id, body="该止盈没止",
                                  tags="情绪误判", lesson_ref="L-退潮-减仓"))
    assert r.review_id is not None and r.created_at == FIXED
    got = repo.reviews_for_session(s.session_id)
    assert got[0].lesson_ref == "L-退潮-减仓"


def test_account_daily_upsert(repo):
    repo.upsert_account_daily(AccountDaily(trade_date=date(2026, 6, 23), equity=100000.0))
    repo.upsert_account_daily(AccountDaily(trade_date=date(2026, 6, 23), equity=101000.0))
    a = repo.account_daily(date(2026, 6, 23))
    assert a.equity == pytest.approx(101000.0)        # 覆盖而非重复
    assert a.cash is None                              # 未填诚实 None


def test_pattern_winrate_over_closed_positions(repo):
    # 首板:一盈;连板:一亏。各开平一笔。
    repo.record_fill(OpsFill(code="600519", side="buy", price=10.0, qty=100,
                             filled_at=datetime(2026, 6, 23, 9, 30)))
    # 给 600519 持仓打 pattern(直接建仓无决策 → pattern 空,手动用 review 不影响)。
    # 这里改用带决策的路径验证 pattern 归属:
    s = repo.create_session(OpsSession(trade_date=date(2026, 6, 22)))
    [c1] = repo.add_candidates(s.session_id, [
        OpsCandidate(session_id=s.session_id, code="000001", rank=1, pattern="连板")])
    d1 = repo.confirm_decision(s.session_id, c1.candidate_id, intent_side="buy")
    repo.record_fill(OpsFill(decision_id=d1.decision_id, code="000001", side="buy",
                             price=20.0, qty=100, filled_at=datetime(2026, 6, 23, 9, 30)))
    repo.record_fill(OpsFill(code="000001", side="sell", price=18.0, qty=100,
                             filled_at=datetime(2026, 6, 24, 14, 0)))
    rows = repo.pattern_winrate()
    lianban = next(r for r in rows if r["pattern"] == "连板")
    assert lianban["closed"] == 1 and lianban["wins"] == 0
    assert lianban["avg_pnl"] == pytest.approx((18.0 - 20.0) * 100)


def test_full_lifecycle_on_file_db(tmp_path):
    path = tmp_path / "youzi.db"
    db = Database(path)
    db.migrate()
    repo = OpsRepository(db, clock=lambda: FIXED)

    s = repo.create_session(OpsSession(trade_date=date(2026, 6, 22), regime_read="主升"))
    [c] = repo.add_candidates(s.session_id, [
        OpsCandidate(session_id=s.session_id, code="600519", rank=1, pattern="首板",
                     plan_entry=10.0)])
    d = repo.confirm_decision(s.session_id, c.candidate_id, intent_side="buy",
                              planned_price=10.0, planned_qty=200)
    # 分两批买入
    repo.record_fill(OpsFill(decision_id=d.decision_id, code="600519", side="buy",
                             price=10.0, qty=100, filled_at=datetime(2026, 6, 23, 9, 30)))
    _, pos = repo.record_fill(OpsFill(decision_id=d.decision_id, code="600519", side="buy",
                                      price=12.0, qty=100,
                                      filled_at=datetime(2026, 6, 23, 13, 0)))
    assert pos.qty_open == 200 and pos.avg_cost == pytest.approx(11.0)
    # 部分平仓
    _, pos = repo.record_fill(OpsFill(code="600519", side="sell", price=13.0, qty=100,
                                      filled_at=datetime(2026, 6, 24, 14, 0)))
    assert pos.qty_open == 100 and pos.status == "open"
    assert pos.realized_pnl == pytest.approx((13.0 - 11.0) * 100)
    repo.add_review(OpsReview(session_id=s.session_id, position_id=pos.position_id,
                              body="减半仓", tags="主升兑现"))
    repo.upsert_account_daily(AccountDaily(trade_date=date(2026, 6, 24),
                                           realized_pnl_day=200.0))
    db.close()

    # 跨连接重开,数据仍在
    db2 = Database(path)
    repo2 = OpsRepository(db2)
    assert repo2.get_session(s.session_id).regime_read == "主升"
    assert repo2.open_position_for("600519").qty_open == 100
    assert repo2.account_daily(date(2026, 6, 24)).realized_pnl_day == pytest.approx(200.0)
    db2.close()
