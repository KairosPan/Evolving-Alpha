# tests/test_agent_run_repo.py
"""AgentRun 状态机:单向不可逆,非法转移抛错而非静默 no-op。"""
from datetime import date

import pytest

from youzi.store.agent_run_repo import AgentRunRepository
from youzi.store.db import connect
from youzi.store.errors import IllegalTransitionError, NotFoundError

D = date(2024, 6, 26)


@pytest.fixture
def repo():
    return AgentRunRepository(connect(":memory:"))


def _new(repo, **kw):
    return repo.create(trade_date=D, strategy_id="llm_agent", **kw)


def test_create_lands_pending_with_context(repo):
    run = _new(repo, account_id="A", account_context={"cash": 1.0},
               harness_snapshot_ref="seed", model="mock")
    assert run.status == "pending" and run.finished_at is None
    assert run.account_context() == {"cash": 1.0}
    assert repo.get(run.run_id).run_id == run.run_id
    assert repo.get("nope") is None


def test_happy_path_pending_running_succeeded(repo):
    run = _new(repo)
    assert repo.mark_running(run.run_id).status == "running"
    done = repo.mark_succeeded(run.run_id, raw_output="{}", parsed_output={"a": 1})
    assert done.status == "succeeded" and done.finished_at is not None
    assert done.parsed_output() == {"a": 1}


def test_pending_can_fail_directly(repo):
    run = _new(repo)
    failed = repo.mark_failed(run.run_id, error="boom")
    assert failed.status == "failed" and failed.error == "boom"


@pytest.mark.parametrize("path, illegal", [
    ([], "succeeded"),                                # pending 不能跳过 running
    (["mark_running", "mark_succeeded"], "running"),  # succeeded 是终态
    (["mark_running", "mark_succeeded"], "failed"),
    (["mark_failed"], "running"),                     # failed 是终态
    (["mark_failed"], "succeeded"),
    (["mark_running"], "running"),                    # 不可自转移
])
def test_illegal_transitions_raise(repo, path, illegal):
    run = _new(repo)
    for step in path:
        getattr(repo, step)(run.run_id, **({"error": "x"} if step == "mark_failed" else {}))
    before = repo.get(run.run_id).status
    with pytest.raises(IllegalTransitionError):
        getattr(repo, f"mark_{illegal}")(
            run.run_id, **({"error": "x"} if illegal == "failed" else {}))
    assert repo.get(run.run_id).status == before      # 非法转移不得留下副作用


def test_unknown_run_raises_not_found(repo):
    with pytest.raises(NotFoundError):
        repo.require("nope")
    with pytest.raises(NotFoundError):
        repo.mark_running("nope")


def test_adopt_only_from_succeeded_and_only_once(repo):
    run = _new(repo)
    with pytest.raises(IllegalTransitionError):        # pending 不可采纳
        repo.mark_adopted(run.run_id)
    repo.mark_running(run.run_id)
    repo.mark_failed(run.run_id, error="x")
    with pytest.raises(IllegalTransitionError):        # failed 不可采纳
        repo.mark_adopted(run.run_id)

    ok = _new(repo)
    repo.mark_running(ok.run_id)
    repo.mark_succeeded(ok.run_id, raw_output="{}")
    adopted = repo.mark_adopted(ok.run_id)
    assert adopted.adopted_at is not None
    with pytest.raises(IllegalTransitionError, match="已采纳"):
        repo.mark_adopted(ok.run_id)


def test_list_by_date_filters_and_orders(repo):
    a = _new(repo)
    b = repo.create(trade_date=date(2024, 6, 27), strategy_id="llm_agent")
    ids = [r.run_id for r in repo.list_by_date(D)]
    assert ids == [a.run_id]
    assert [r.run_id for r in repo.list_by_date(date(2024, 6, 27))] == [b.run_id]
    assert repo.list_by_date(date(2024, 6, 28)) == []


def test_prompt_fingerprint_is_metadata_not_a_transition(repo):
    run = _new(repo)
    repo.set_prompt_fingerprint(run.run_id, "abc123")
    assert repo.get(run.run_id).prompt_fingerprint == "abc123"
    assert repo.get(run.run_id).status == "pending"     # 状态不受影响


def test_corrupt_json_columns_degrade_to_empty(repo):
    """损坏的 JSON 列不该让读模型崩(审计读路径必须抗脏数据)。"""
    run = _new(repo)
    repo._conn.execute(            # noqa: SLF001 — 测试故意写脏数据
        "UPDATE agent_run SET account_context_json='{bad', parsed_output_json='[1,2]'"
        " WHERE run_id = ?", (run.run_id,))
    repo._conn.commit()            # noqa: SLF001
    got = repo.get(run.run_id)
    assert got.account_context() == {} and got.parsed_output() == {}
