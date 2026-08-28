# tests/test_ops_repo.py
"""OpsRepository:一天一单(UNIQUE)、采纳原子性、人工确认唯一。"""
from datetime import date

import pytest

from youzi.store.agent_run_repo import AgentRunRepository
from youzi.store.db import connect
from youzi.store.errors import DuplicateError, IllegalTransitionError, NotFoundError
from youzi.store.ops_repo import OpsRepository

D = date(2024, 6, 26)


@pytest.fixture
def repos():
    conn = connect(":memory:")
    return AgentRunRepository(conn), OpsRepository(conn)


def _succeeded_run(runs, account_id="A", trade_date=D):
    run = runs.create(trade_date=trade_date, strategy_id="llm_agent", account_id=account_id)
    runs.mark_running(run.run_id)
    return runs.mark_succeeded(run.run_id, raw_output="{}")


_CANDS = [
    {"code": "600000", "name": "甲", "pattern": "p1", "score": 0.8, "reason": "龙头",
     "plan": {"trigger": "t"}, "check_status": "ok", "check": {"status": "ok"}},
    {"code": "300001", "name": "乙", "pattern": "p2", "score": 0.4,
     "check_status": "blocked", "check": {"status": "blocked", "reasons": ["现金不足"]}},
]


def test_adopt_writes_session_candidates_and_stamps_run(repos):
    runs, ops = repos
    run = _succeeded_run(runs)
    sess = ops.adopt_run(run_id=run.run_id, account_id="A", trade_date=D, candidates=_CANDS)
    assert sess.account_id == "A" and sess.trade_date == D
    assert [c.code for c in sess.candidates] == ["600000", "300001"]
    assert [c.rank for c in sess.candidates] == [0, 1]
    assert sess.candidates[0].plan() == {"trigger": "t"}
    assert runs.get(run.run_id).adopted_at is not None


def test_blocked_candidates_are_kept_not_dropped(repos):
    """校验不过的候选必须留在单上并标记原因——静默丢弃会让人看不见系统为何否掉。"""
    runs, ops = repos
    sess = ops.adopt_run(run_id=_succeeded_run(runs).run_id, account_id="A",
                         trade_date=D, candidates=_CANDS)
    blocked = [c for c in sess.candidates if c.check_status == "blocked"]
    assert len(blocked) == 1 and blocked[0].code == "300001"
    assert blocked[0].check()["reasons"] == ["现金不足"]


def test_one_session_per_account_per_day(repos):
    runs, ops = repos
    r1, r2 = _succeeded_run(runs), _succeeded_run(runs)
    ops.adopt_run(run_id=r1.run_id, account_id="A", trade_date=D, candidates=[])
    with pytest.raises(DuplicateError):
        ops.adopt_run(run_id=r2.run_id, account_id="A", trade_date=D, candidates=[])


def test_duplicate_adopt_rolls_back_the_stamp(repos):
    """UNIQUE 冲突必须整事务回滚:第二次运行不该留下 adopted_at 却没有单子。"""
    runs, ops = repos
    r1, r2 = _succeeded_run(runs), _succeeded_run(runs)
    ops.adopt_run(run_id=r1.run_id, account_id="A", trade_date=D, candidates=[])
    with pytest.raises(DuplicateError):
        ops.adopt_run(run_id=r2.run_id, account_id="A", trade_date=D, candidates=_CANDS)
    assert runs.get(r2.run_id).adopted_at is None
    assert ops.session_for("A", D).agent_run_id == r1.run_id


def test_other_account_or_day_is_fine(repos):
    runs, ops = repos
    ops.adopt_run(run_id=_succeeded_run(runs).run_id, account_id="A",
                  trade_date=D, candidates=[])
    ops.adopt_run(run_id=_succeeded_run(runs, "B").run_id, account_id="B",
                  trade_date=D, candidates=[])
    other = date(2024, 6, 27)
    ops.adopt_run(run_id=_succeeded_run(runs, trade_date=other).run_id,
                  account_id="A", trade_date=other, candidates=[])
    assert ops.session_for("A", D) is not None and ops.session_for("B", D) is not None


def test_adopt_rejects_non_succeeded_and_re_adopt(repos):
    runs, ops = repos
    pending = runs.create(trade_date=D, strategy_id="s", account_id="A")
    with pytest.raises(IllegalTransitionError):
        ops.adopt_run(run_id=pending.run_id, account_id="A", trade_date=D, candidates=[])
    assert ops.session_for("A", D) is None            # 拒绝时不留半个单子

    run = _succeeded_run(runs)
    ops.adopt_run(run_id=run.run_id, account_id="A", trade_date=D, candidates=[])
    with pytest.raises(IllegalTransitionError):        # 重复采纳
        ops.adopt_run(run_id=run.run_id, account_id="A", trade_date=date(2024, 6, 27),
                      candidates=[])


def test_duplicate_code_in_one_session_rejected(repos):
    runs, ops = repos
    dup = [{"code": "600000", "check_status": "ok"}, {"code": "600000", "check_status": "ok"}]
    with pytest.raises(DuplicateError):
        ops.adopt_run(run_id=_succeeded_run(runs).run_id, account_id="A",
                      trade_date=D, candidates=dup)


def test_confirm_is_once_per_candidate(repos):
    runs, ops = repos
    sess = ops.adopt_run(run_id=_succeeded_run(runs).run_id, account_id="A",
                         trade_date=D, candidates=_CANDS)
    cid = sess.candidates[0].candidate_id
    d = ops.confirm(candidate_id=cid, action="buy", note="人已确认")
    assert d.action == "buy" and d.session_id == sess.session_id
    with pytest.raises(DuplicateError):
        ops.confirm(candidate_id=cid, action="skip")
    assert [x.action for x in ops.decisions(sess.session_id)] == ["buy"]


def test_confirm_unknown_candidate_is_not_found(repos):
    _, ops = repos
    with pytest.raises(NotFoundError):
        ops.confirm(candidate_id="nope", action="buy")


def test_require_session_raises_not_found(repos):
    _, ops = repos
    assert ops.get_session("nope") is None
    with pytest.raises(NotFoundError):
        ops.require_session("nope")
