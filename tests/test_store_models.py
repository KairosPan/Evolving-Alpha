from datetime import date, datetime

from youzi.store.models import (
    AccountDaily, OpsCandidate, OpsDecision, OpsFill,
    OpsPosition, OpsReview, OpsSession,
)


def test_session_defaults_and_honest_none():
    s = OpsSession(trade_date=date(2026, 6, 22))
    assert s.session_id is None
    assert s.regime_read == ""
    assert s.harness_version is None        # 缺失诚实 None,不臆造 0
    assert s.decision_run_ref is None


def test_candidate_plan_prices_optional():
    c = OpsCandidate(session_id=1, code="600519", rank=1)
    assert c.confidence == 0.5
    assert c.plan_entry is None and c.plan_stop is None and c.plan_target is None
    assert c.raw is None


def test_fill_requires_price_qty_filled_at():
    f = OpsFill(code="600519", side="buy", price=10.0, qty=100,
               filled_at=datetime(2026, 6, 23, 9, 30))
    assert f.fee is None                    # 没填费 → None
    assert f.position_id is None


def test_position_and_review_and_account_defaults():
    p = OpsPosition(code="600519", opened_on=date(2026, 6, 23))
    assert p.status == "open" and p.qty_open == 0 and p.realized_pnl == 0.0
    r = OpsReview()
    assert r.session_id is None and r.position_id is None and r.lesson_ref is None
    a = AccountDaily(trade_date=date(2026, 6, 23))
    assert a.equity is None and a.unrealized_pnl is None
