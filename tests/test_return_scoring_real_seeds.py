# tests/test_return_scoring_real_seeds.py
"""真实种子(seeds/)上的 C3 可成交收益打分端到端:act→ReturnScorer 延迟打分→在线信用。

C3 语义:
- 被选真实技能(一进二/relay_1to2)的候选 A 每日涨停(outcome 仍池类别 continued)且带
  覆盖决策日(prev_close)+entry+exit 的 OHLCV → sc.score = 可成交净收益(非 {1,0,−1});
- 同被选的候选 Z 也每日涨停但**无 OHLCV** → 记 outcome='missing'(C3:一等公民,不再静默丢弃,
  但不计入 mean/n_candidates、不归因信用);
- EvalReport:mean_score = 平均净收益(filled 口径)、hit_rate = 池 continued 率、n_missing=Z 计数;
- apply_credit 后真实技能 SkillStats.expectancy_raw = 平均净收益(missing 的 Z 不归因);
  expectancy(C2=advantage)= 0,因池净收益基线恰=A 自身(Z 无数据被剔出基线)。
全离线(FakeSource + MockLLMClient,refiner 空 ops)。horizon=2(T+1 合规)。
"""
from datetime import date, timedelta

import pandas as pd

from youzi.eval.fill import CostModel
from youzi.eval.scorer import ReturnScorer
from youzi.eval.walk_forward import report_from_trajectory
from youzi.harness.loader import load_seeds
from youzi.harness.manager import HarnessManager
from youzi.harness.snapshot import SnapshotStore
from youzi.llm.client import MockLLMClient
from youzi.loop.inner_loop import InnerLoop, LoopConfig
from tests.conftest import FakeSource

SEED_SKILL_NAME = "一进二"          # relay_1to2.name_cn(agent pattern 走 name_cn 解析归因)
SEED_SKILL_ID = "relay_1to2"

SCORED_CODE = "A"                   # 每日涨停 + 全程 OHLCV → ReturnScorer 净收益打分
MISSING_CODE = "Z"                  # 每日涨停但无 OHLCV → outcome='missing'(不丢弃、不归因)

_DAYS = [date(2024, 6, 26) + timedelta(days=k) for k in range(4)]   # n=4 交易日
_COST = CostModel().round_trip_cost()

# A 普通成交(开盘=prev_close,ratio=0):决策 _DAYS[0] → entry _DAYS[1] fill@10、exit _DAYS[2] close=11;
#                                       决策 _DAYS[1] → entry _DAYS[2] fill@10、exit _DAYS[3] close=12。
_A_OHLCV = [(_DAYS[0], 10.0, 10.5, 9.5, 10.0, 100),
            (_DAYS[1], 10.0, 10.5, 9.5, 10.0, 100),
            (_DAYS[2], 10.0, 11.5, 9.5, 11.0, 100),
            (_DAYS[3], 11.0, 12.5, 10.5, 12.0, 100)]
_NET0 = (11.0 - 10.0) / 10.0 - _COST       # 决策 _DAYS[0]
_NET1 = (12.0 - 10.0) / 10.0 - _COST       # 决策 _DAYS[1]
_EXPECTED_NETS = [_NET0, _NET1]
_MEAN_NET = sum(_EXPECTED_NETS) / len(_EXPECTED_NETS)


def _src() -> FakeSource:
    """A、Z 每日同时涨停(均池 continued);只有 A 带 OHLCV。"""
    frames = {("zt", d): pd.DataFrame({"code": [SCORED_CODE, MISSING_CODE],
                                       "name": ["甲", "乙"], "boards": [2, 2]})
              for d in _DAYS}
    ohlcv = {SCORED_CODE: pd.DataFrame(
        _A_OHLCV, columns=["date", "open", "high", "low", "close", "volume"])}
    return FakeSource(frames, _DAYS, ohlcv=ohlcv)


def _decision() -> str:
    """同时选 A、Z,pattern 用真实种子技能 name_cn(在线信用归因到 relay_1to2)。"""
    return ('{"candidates": ['
            '{"code": "%s", "pattern": "%s", "confidence": 0.7},'
            '{"code": "%s", "pattern": "%s", "confidence": 0.7}],'
            ' "no_trade_reason": ""}') % (
        SCORED_CODE, SEED_SKILL_NAME, MISSING_CODE, SEED_SKILL_NAME)


def test_real_seeds_return_scoring_end_to_end(tmp_path):
    n = len(_DAYS)
    src = _src()
    h = load_seeds("seeds/")
    mgr = HarnessManager(h, SnapshotStore(tmp_path))
    sk = mgr.harness.skills.get(SEED_SKILL_ID)
    assert sk is not None and sk.name_cn == SEED_SKILL_NAME
    assert sk.stats.n == 0 and sk.stats.expectancy is None

    loop = InnerLoop(
        mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
        MockLLMClient([_decision()]), MockLLMClient(['{"ops": []}']),
        config=LoopConfig(horizon=2, breaker_min_days=10_000),   # T+1 合规;不熔断,聚焦打分
        scorer=ReturnScorer(),
    )
    rep = loop.run()

    # ── ① 轨迹:n 步,horizon=2 → 前 n−2 步已打分,末两步未打分 ──
    assert rep.trajectory.n_decisions() == n
    scored = rep.trajectory.scored_steps()
    assert len(scored) == n - 2
    assert rep.trajectory.steps[-1].scored is False

    # ── ① sc.score = 可成交净收益(非池 SCORE {1,0,−1});outcome 仍池类别 continued ──
    got = [s.outcomes[SCORED_CODE].score for s in scored]
    assert got == _EXPECTED_NETS
    for s in scored:
        sc = s.outcomes[SCORED_CODE]
        assert sc.outcome == "continued"
        assert sc.settle == "normal"
        assert sc.score not in (1.0, 0.0, -1.0)

    # ── ② 无 OHLCV 的 Z:C3 记 'missing'(一等公民,不静默丢弃,但 score=0)──
    for s in scored:
        assert set(s.outcomes) == {SCORED_CODE, MISSING_CODE}
        assert s.outcomes[MISSING_CODE].outcome == "missing"
        assert s.outcomes[MISSING_CODE].score == 0.0

    # ── ③ EvalReport:真实成交仅 A;Z 计入 n_missing、不入 mean/n_candidates ──
    er = report_from_trajectory(rep.trajectory)
    assert er.n_candidates == n - 2                  # 仅 A(两步)
    assert er.n_missing == n - 2                      # Z 两步均缺数
    assert er.fill_rate == 1.0                        # 无 unfillable
    assert abs(er.mean_score - _MEAN_NET) < 1e-9      # 平均净收益(filled)
    assert er.hit_rate == 1.0 and er.nuke_rate == 0.0

    # ── ④ apply_credit:仅 A 归因(Z=missing 跳过);expectancy_raw=净收益均值,expectancy(超额)=0 ──
    st = mgr.harness.skills.get(SEED_SKILL_ID).stats
    assert st.n == n - 2 and st.wins == n - 2         # 仅 A 计入(Z missing 不归因)
    assert st.expectancy is not None and abs(st.expectancy) < 1e-9   # 基线=A 自身净收益 → 超额 0
    assert st.expectancy_raw is not None
    assert abs(st.expectancy_raw - _MEAN_NET) < 1e-9
    assert st.expectancy_raw != 1.0                   # 反证:池 SCORE 打分会给 1.0
