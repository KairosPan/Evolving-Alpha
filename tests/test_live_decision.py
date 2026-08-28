# tests/test_live_decision.py
"""LiveDecisionService 端到端(全离线:FakeSource + MockLLMClient)。"""
from datetime import date

import pandas as pd
import pytest

from tests.conftest import FakeSource
from youzi.application.live_decision import (
    LiveDecisionService,
    StrategyNotFoundError,
    check_candidate,
)
from youzi.llm.client import MockLLMClient
from youzi.replay.firewall import LookaheadError
from youzi.store.account_repo import AccountRepo
from youzi.store.agent_run_repo import AgentRunRepository
from youzi.store.db import connect
from youzi.store.errors import DuplicateError, IllegalTransitionError, NotFoundError
from youzi.store.ops_repo import OpsRepository

D = date(2024, 6, 26)
D1 = date(2024, 6, 27)
PICK_A = ('{"regime_read":"主升","candidates":[{"code":"600000","pattern":"highest_board",'
          '"reason":"最高板","confidence":0.8}],"no_trade_reason":""}')


def _source(days=(D, D1)):
    """每日 600000 涨停、300001 炸板;两者都有 t 日 OHLCV。"""
    frames = {}
    for d in days:
        frames[("zt", d)] = pd.DataFrame(
            {"code": ["600000"], "name": ["甲"], "boards": [3], "pct": [10.0]})
        frames[("blowup", d)] = pd.DataFrame(
            {"code": ["300001"], "name": ["乙"], "boards": [0], "pct": [3.0]})
        frames[("dt", d)] = pd.DataFrame()
        frames[("prev", d)] = pd.DataFrame()
    ohlcv = {c: pd.DataFrame({"date": list(days), "open": [10.0] * len(days),
                              "high": [11.0] * len(days), "low": [9.5] * len(days),
                              "close": [11.0] * len(days), "volume": [1] * len(days)})
             for c in ("600000", "300001")}
    return FakeSource(frames, list(days), ohlcv)


def _service(llm=None, source=None, **kw):
    conn = connect(":memory:")
    return LiveDecisionService(
        source=source or _source(), llm=llm or MockLLMClient(PICK_A),
        agent_runs=AgentRunRepository(conn), accounts=AccountRepo(conn),
        ops=OpsRepository(conn), model="mock", temperature=0.0, **kw)


class BoomLLM:
    """必炸的 LLM(模拟 DeepSeek 连不上/超时)。"""
    def complete(self, system, user):
        raise RuntimeError("上游 502")


# ── run ──────────────────────────────────────────────────────────────────
def test_run_freezes_market_account_and_harness(tmp_path):
    svc = _service()
    svc.record_fill(operation_id="seed-cash", account_id="A", trade_date=D,
                    code="600000", side="buy", price=10.0, qty=100)
    run = svc.run(D, "seed", "A")

    assert run.status == "succeeded" and run.error is None
    assert run.trade_date == D and run.account_id == "A"
    assert run.harness_snapshot_ref == "seed" and run.strategy_id == "llm_agent"
    assert run.model == "mock" and run.temperature == 0.0
    assert run.market_as_of == "2024-06-26T15:00:00"      # 收盘快照戳
    assert run.snapshot_ref == "FakeSource@2024-06-26"
    assert len(run.prompt_fingerprint) == 16
    assert run.raw_output == PICK_A                        # 原文留痕
    # 账户在决策时刻被冻结进 run(此后校验只认这份)
    ctx = run.account_context()
    assert ctx["account_id"] == "A" and ctx["positions"]["600000"]["qty"] == 100
    # 结构化决策 + 候选的 ≤t 入场事实
    parsed = run.parsed_output()
    assert [c["code"] for c in parsed["decision"]["candidates"]] == ["600000"]
    entry = parsed["entries"]["600000"]
    assert entry["status"] == "limit_up" and entry["close"] == 11.0
    assert entry["limit_pct"] == pytest.approx(0.10)       # 主板 10cm


def test_run_freezes_account_snapshot_row(tmp_path):
    conn = connect(":memory:")
    accounts = AccountRepo(conn)
    svc = LiveDecisionService(source=_source(), llm=MockLLMClient(PICK_A),
                              agent_runs=AgentRunRepository(conn), accounts=accounts,
                              ops=OpsRepository(conn))
    run = svc.run(D, "seed", "A")
    snaps = accounts.snapshots("A")
    assert [s.source for s in snaps] == ["frozen"]
    # 账务时间轴(冻结墙钟)独立于行情时间轴(收盘戳),两者都留痕且不混用
    assert snaps[0].as_of == run.account_context()["as_of"]
    assert run.market_as_of == "2024-06-26T15:00:00"
    assert accounts.latest_baseline("A") is None      # frozen 不当折叠基线


def test_agent_gets_no_source_or_db_handle():
    """防火墙:agent 只拿冻结对象。提示里出现的是盘面文本,不是任何句柄。"""
    llm = MockLLMClient(PICK_A)
    _service(llm=llm).run(D, "seed", "A")
    system, user = llm.calls[0]
    assert "纪律红线" in system                     # H 真的被渲染进系统提示
    assert "600000" in user                          # 候选池以文本形式给到
    assert "FakeSource" not in user and "sqlite" not in user.lower()


def test_llm_failure_lands_a_failed_run_not_a_raise():
    svc = _service(llm=BoomLLM())
    run = svc.run(D, "seed", "A")
    assert run.status == "failed"
    assert "上游 502" in run.error and run.finished_at is not None
    assert run.parsed_output() == {}
    assert svc.list_runs(D)[0].run_id == run.run_id   # 失败也留在运行历史里


def test_source_failure_also_lands_failed():
    """取数失败(如 PIT 快照缺池)同样留痕,不裸抛——没有记录的失败最危险。"""
    from youzi.data.snapshot_source import SnapshotMissingError

    class BrokenSource(FakeSource):
        def zt_pool(self, day):
            raise SnapshotMissingError("快照缺池 zt")

    src = _source()
    broken = BrokenSource(src._frames, src._calendar, src._ohlcv)   # noqa: SLF001
    run = _service(source=broken).run(D, "seed", "A")
    assert run.status == "failed" and "快照缺池" in run.error


def test_empty_pools_are_a_legal_no_trade_day_not_a_crash():
    """全空池 = 冰点没票,是合法状态,不该崩成 failed。"""
    src = FakeSource({}, [D], {})
    run = _service(source=src, llm=MockLLMClient('{"candidates":[]}')).run(D, "seed", "A")
    assert run.status == "succeeded"
    assert run.parsed_output()["decision"]["candidates"] == []


def test_unknown_strategy_version_raises_before_creating_run():
    svc = _service()
    with pytest.raises(StrategyNotFoundError):
        svc.run(D, "does-not-exist", "A")
    assert svc.list_runs(D) == []                     # 参数错不污染运行历史


def test_snapshot_strategy_version_requires_store(tmp_path):
    svc = _service()
    with pytest.raises(StrategyNotFoundError, match="SnapshotStore"):
        svc.run(D, "snapshot:1", "A")


def test_harness_snapshot_version_is_loaded_and_recorded(tmp_path):
    from youzi.harness.edit_log import EditLog
    from youzi.harness.loader import load_seeds
    from youzi.harness.snapshot import SnapshotStore
    from youzi.application.live_decision import _default_seeds_dir

    store = SnapshotStore(tmp_path / "snaps")
    version = store.save(load_seeds(_default_seeds_dir()), EditLog(), label="t")
    svc = _service(snapshot_store=store)
    run = svc.run(D, f"snapshot:{version}", "A")
    assert run.status == "succeeded"
    assert run.harness_snapshot_ref == f"snapshot:{version}"
    versions = [s["version"] for s in svc.list_strategies()]
    assert versions == ["seed", f"snapshot:{version}"]
    with pytest.raises(StrategyNotFoundError):
        svc.run(D, "snapshot:999", "A")
    with pytest.raises(StrategyNotFoundError):
        svc.run(D, "snapshot:abc", "A")


def test_firewall_blocks_future_market_snapshot():
    """market_snapshot 经 GuardedSource:越界取未来 → LookaheadError。"""
    svc = _service()
    snap = svc.market_snapshot(D)
    assert snap["universe"]["n"] == 2 and snap["state"]["date"] == "2024-06-26"
    assert snap["universe"]["limit_up"] == 1 and snap["universe"]["blowup"] == 1
    assert snap["as_of"] == "2024-06-26T15:00:00"
    # 同一把 guard 下,请求 t 之后的任何一天都被拦(未来函数不因 live 路径开后门)
    with pytest.raises(LookaheadError):
        svc._guarded(D).zt_pool(D1)                            # noqa: SLF001
    with pytest.raises(LookaheadError):
        svc._guarded(D).daily_ohlcv("600000", D, D1)           # noqa: SLF001


# ── adopt ────────────────────────────────────────────────────────────────
def test_adopt_builds_ops_session_with_checks():
    svc = _service()
    run = svc.run(D, "seed", "A")
    sess = svc.adopt(run.run_id)
    assert sess.account_id == "A" and sess.trade_date == D
    assert [c.code for c in sess.candidates] == ["600000"]
    c = sess.candidates[0]
    assert c.pattern == "highest_board" and c.score == pytest.approx(0.8)
    chk = c.check()
    assert chk["ref_price"] == 11.0
    assert chk["limit_price_next"] == pytest.approx(12.1)      # 11 × 1.10
    assert chk["one_word_risk"] is True                        # t 日封板 → 提示风险
    assert svc.get_run(run.run_id).adopted_at is not None


def test_adopt_rejects_non_succeeded_runs():
    svc = _service(llm=BoomLLM())
    failed = svc.run(D, "seed", "A")
    with pytest.raises(IllegalTransitionError):
        svc.adopt(failed.run_id)
    with pytest.raises(NotFoundError):
        svc.adopt("no-such-run")


def test_adopt_is_once_per_run_and_once_per_day():
    svc = _service(llm=MockLLMClient([PICK_A, PICK_A]))
    r1 = svc.run(D, "seed", "A")
    svc.adopt(r1.run_id)
    with pytest.raises(IllegalTransitionError):        # 同一 run 重复采纳
        svc.adopt(r1.run_id)
    r2 = svc.run(D, "seed", "A")
    with pytest.raises(DuplicateError):               # 同账户同日已有单
        svc.adopt(r2.run_id)


def test_adopt_marks_blocked_candidate_instead_of_dropping():
    """现金不足的候选留在单上标 blocked,人看得见系统为何否掉。"""
    conn = connect(":memory:")
    accounts = AccountRepo(conn)
    accounts.put_snapshot(account_id="A", as_of="2024-06-25T15:00:00", cash=100.0,
                          positions={}, source="manual")       # 只有 100 元
    svc = LiveDecisionService(source=_source(), llm=MockLLMClient(PICK_A),
                              agent_runs=AgentRunRepository(conn), accounts=accounts,
                              ops=OpsRepository(conn))
    sess = svc.adopt(svc.run(D, "seed", "A").run_id)
    assert len(sess.candidates) == 1                            # 没被丢掉
    c = sess.candidates[0]
    assert c.check_status == "blocked"
    assert any("现金" in r for r in c.check()["reasons"])


def test_adopt_uses_only_the_frozen_account_context():
    """冻结纪律:run 之后账户再变化,adopt 的校验也只认冻结那一刻的 JSON。"""
    conn = connect(":memory:")
    accounts = AccountRepo(conn)
    accounts.put_snapshot(account_id="A", as_of="2024-06-25T15:00:00", cash=100.0,
                          positions={}, source="manual")
    svc = LiveDecisionService(source=_source(), llm=MockLLMClient(PICK_A),
                              agent_runs=AgentRunRepository(conn), accounts=accounts,
                              ops=OpsRepository(conn))
    run = svc.run(D, "seed", "A")
    accounts.put_snapshot(account_id="A", as_of="2024-06-26T20:00:00", cash=999999.0,
                          positions={}, source="manual")        # 事后充值
    sess = svc.adopt(run.run_id)
    assert sess.candidates[0].check_status == "blocked"          # 仍按冻结时的 100 元判


def test_adopt_of_no_trade_run_yields_empty_session():
    svc = _service(llm=MockLLMClient('{"candidates":[],"no_trade_reason":"冰点空仓"}'))
    run = svc.run(D, "seed", "A")
    assert run.parsed_output()["decision"]["no_trade_reason"] == "冰点空仓"
    assert svc.adopt(run.run_id).candidates == []


def test_adopt_joins_the_skill_plan_from_the_run_s_harness():
    """候选的 pattern 命中真实种子技能时,可执行计划要跟着上单子(join 不到则降级 None)。"""
    picked = ('{"candidates":[{"code":"600000","pattern":"w2s_weak_to_strong",'
              '"reason":"弱转强","confidence":0.6}]}')
    svc = _service(llm=MockLLMClient(picked))
    sess = svc.adopt(svc.run(D, "seed", "A").run_id)
    plan = sess.candidates[0].plan()
    assert plan["skill_id"] == "w2s_weak_to_strong" and plan["name_cn"] == "弱转强"
    assert "trigger" in plan and isinstance(plan["taboo"], list)


def test_adopt_degrades_when_pattern_matches_no_skill():
    svc = _service(llm=MockLLMClient('{"candidates":[{"code":"600000","pattern":"没这个技能"}]}'))
    sess = svc.adopt(svc.run(D, "seed", "A").run_id)
    assert sess.candidates[0].plan() == {}          # join 不到 → 降级,不编造计划


def test_hallucinated_code_never_reaches_the_ops_session():
    svc = _service(llm=MockLLMClient('{"candidates":[{"code":"ZZZZZZ","pattern":"x"}]}'))
    sess = svc.adopt(svc.run(D, "seed", "A").run_id)
    assert sess.candidates == []                     # parse 的幻觉过滤仍在生效


# ── 确定性校验(纯函数)─────────────────────────────────────────────────
def test_check_candidate_unknown_without_price():
    chk = check_candidate({"code": "600000", "name": "甲", "close": None},
                          {"is_absolute_cash": True, "cash": 1e6})
    assert chk["status"] == "unknown" and chk["checks"]["pricing"] == "unknown"
    assert chk["lot_cost"] is None


def test_check_candidate_ok_with_enough_cash():
    chk = check_candidate({"code": "600000", "name": "甲", "close": 10.0,
                           "status": "blowup"},
                          {"is_absolute_cash": True, "cash": 1e6, "positions": {}})
    assert chk["status"] == "ok"
    assert chk["lot_cost"] == pytest.approx(1100.0)      # 10 × 1.10 × 100 股
    assert chk["one_word_risk"] is False


def test_check_candidate_without_baseline_is_unknown_not_ok():
    """没有绝对现金就不能冒充"资金校验通过"。"""
    chk = check_candidate({"code": "600000", "close": 10.0},
                          {"is_absolute_cash": False, "cash": -50.0})
    assert chk["status"] == "unknown" and chk["checks"]["cash"] == "unknown"


def test_check_candidate_uses_board_specific_limit():
    """创业板 20cm:同一收盘价,一手最坏资金占用更高。"""
    ctx = {"is_absolute_cash": True, "cash": 1e6, "positions": {}}
    main = check_candidate({"code": "600000", "name": "甲", "close": 10.0}, ctx)
    gem = check_candidate({"code": "300001", "name": "乙", "close": 10.0}, ctx)
    assert main["limit_pct"] == pytest.approx(0.10)
    assert gem["limit_pct"] == pytest.approx(0.20)
    assert gem["lot_cost"] > main["lot_cost"]


def test_check_candidate_flags_existing_position_without_blocking():
    chk = check_candidate(
        {"code": "600000", "close": 10.0},
        {"is_absolute_cash": True, "cash": 1e6, "positions": {"600000": {"qty": 500}}})
    assert chk["status"] == "ok" and any("加仓" in r for r in chk["reasons"])


# ── 全链路 run → adopt → confirm → fill ──────────────────────────────────
def test_full_chain_run_adopt_confirm_fill_updates_positions():
    svc = _service()
    run = svc.run(D, "seed", "A")
    sess = svc.adopt(run.run_id)
    cand = sess.candidates[0]

    decision = svc.confirm(cand.candidate_id, "buy", note="人确认")
    assert decision.action == "buy"

    fill, created = svc.record_fill(
        operation_id="op-1", account_id="A", trade_date=D1, code=cand.code,
        side="buy", price=12.1, qty=100, fee=3.0, decision_id=decision.decision_id)
    assert created is True
    again, created2 = svc.record_fill(
        operation_id="op-1", account_id="A", trade_date=D1, code=cand.code,
        side="buy", price=12.1, qty=100, fee=3.0)
    assert created2 is False and again.fill_id == fill.fill_id

    view = svc.account_view("A")
    assert [(p.code, p.qty) for p in view.positions] == [("600000", 100)]
    assert view.cash == pytest.approx(-(12.1 * 100 + 3.0))
    assert view.n_fills == 1                             # 幂等:只入账一次


def test_check_candidate_star_market_uses_200_share_min_lot():
    """科创板最小申报 200 股:资金校验按 200 股算,不按主板一手 100 低估一半。"""
    ctx = {"is_absolute_cash": True, "cash": 20000.0, "positions": {}}
    star = check_candidate({"code": "688001", "name": "科", "close": 100.0}, ctx)
    assert star["lot_size"] == 200
    assert star["lot_cost"] == pytest.approx(24000.0)     # 100×1.20 涨停价 × 200 股
    assert star["checks"]["cash"] == "blocked"
    main_board = check_candidate({"code": "600519", "name": "甲", "close": 100.0}, ctx)
    assert main_board["lot_size"] == 100
    assert main_board["checks"]["cash"] == "ok"           # 110 × 100 = 11000 ≤ 20000
