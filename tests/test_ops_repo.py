from datetime import date, datetime

import pytest

from youzi.store.db import Database
from youzi.store.models import OpsCandidate, OpsDecision, OpsSession
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
