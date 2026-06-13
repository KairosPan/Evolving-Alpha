from __future__ import annotations

from datetime import date as Date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from youzi.eval.oracle import NON_TRADE_OUTCOMES, Outcome


class ScoredCandidate(BaseModel):
    """一名已评分候选。

    score=原始分(PoolScorer=SCORE[outcome];ReturnScorer=前向收益);
    day_baseline=决策日 limit_up 池基线(同 scorer 口径;空池/缺基线日 None);
    advantage=score−day_baseline(截面超额,去当日市场β;baseline None 时回退=score)。
    """
    model_config = ConfigDict(frozen=True)
    decision_date: Date
    code: str
    pattern: str
    outcome: Outcome
    score: float
    day_baseline: float | None = None   # 决策日池基线(空池日约定:None)
    advantage: float                    # 省略时由 _fill_advantage 回填(兼容旧 JSON/手工构造)
    # C3:成交结算口径。""=池制/不适用;"normal"=开盘或开板涨停价成交;
    # "stop_on_nuke"=持有路径首个 nuked 日(T+1 顺延)砍仓结算(跌停价可成交=乐观近似)。
    settle: str = ""

    @model_validator(mode="before")
    @classmethod
    def _fill_advantage(cls, data: Any) -> Any:
        """advantage 缺省回填:有基线= score−day_baseline;无基线回退= score(旧 JSON 兼容)。"""
        if isinstance(data, dict) and data.get("advantage") is None and data.get("score") is not None:
            base = data.get("day_baseline")
            adv = data["score"] - base if base is not None else data["score"]
            data = {**data, "advantage": adv}
        return data


class PatternStat(BaseModel):
    model_config = ConfigDict(frozen=True)
    n: int
    hit_rate: float
    nuke_rate: float
    mean_score: float


class EvalReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    n_decisions: int
    n_no_trade: int
    n_candidates: int        # 真实成交候选数(continued/faded/nuked;C3:unfillable/missing 不计入)
    horizon: int = 1         # 延迟打分窗口(尾部不足 horizon 的决策被丢弃)
    hit_rate: float          # continued / n_candidates
    nuke_rate: float         # nuked / n_candidates
    mean_score: float        # 期望分(filled 口径:仅真实成交;ReturnScorer 下=可成交净收益均值)
    mean_excess: float = 0.0  # 截面超额均值(真实成交 advantage 均值;旧 JSON 无此字段 → 0.0)
    # ── C3 可成交性敏感度(池制下恒中性:n_unfillable=n_missing=0、fill_rate=1、all_in==mean_score)──
    n_unfillable: int = 0    # 选了买不到的票(一字板等)——"选了多少买不到的"首次成一等指标
    n_missing: int = 0       # 无 OHLCV(停牌/未捕获)——数据缺口,不计入任何收益口径
    fill_rate: float = 1.0   # 成交率 = n_candidates / (n_candidates + n_unfillable);无成交尝试 → 1.0
    mean_score_all_in: float = 0.0  # all-in 口径:真实成交 + unfillable 计 0(missing 仍排除)
    by_pattern: dict[str, PatternStat] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _backfill_all_in(cls, data: Any) -> Any:
        """旧 run-store JSON 无 mean_score_all_in → 回填=mean_score(池制无 unfillable,两口径相等)。"""
        if (isinstance(data, dict) and "mean_score_all_in" not in data
                and data.get("mean_score") is not None):
            data = {**data, "mean_score_all_in": data["mean_score"]}
        return data


def _agg(items: list[ScoredCandidate]) -> tuple[float, float, float, float]:
    """对**真实成交**候选返回 (hit_rate, nuke_rate, mean_score, mean_excess);空列表全 0。"""
    n = len(items)
    if n == 0:
        return (0.0, 0.0, 0.0, 0.0)
    hits = sum(1 for s in items if s.outcome == "continued")
    nukes = sum(1 for s in items if s.outcome == "nuked")
    mean = sum(s.score for s in items) / n
    excess = sum(s.advantage for s in items) / n
    return (hits / n, nukes / n, mean, excess)


def build_report(scored: list[ScoredCandidate], n_decisions: int,
                 n_no_trade: int, horizon: int = 1) -> EvalReport:
    # C3:把 unfillable/missing 从均值与 n_candidates 剔除,单列计数(绝不静默丢弃)
    real = [s for s in scored if s.outcome not in NON_TRADE_OUTCOMES]
    n_unfillable = sum(1 for s in scored if s.outcome == "unfillable")
    n_missing = sum(1 for s in scored if s.outcome == "missing")
    hit, nuke, mean, excess = _agg(real)
    n_real = len(real)
    denom = n_real + n_unfillable
    fill_rate = n_real / denom if denom > 0 else 1.0
    all_in_n = n_real + n_unfillable
    all_in = sum(s.score for s in real) / all_in_n if all_in_n > 0 else 0.0  # unfillable 计 0
    patterns: dict[str, list[ScoredCandidate]] = {}
    for s in real:
        patterns.setdefault(s.pattern, []).append(s)
    by_pattern: dict[str, PatternStat] = {}
    for pat, items in patterns.items():
        h, nk, m, _ = _agg(items)
        by_pattern[pat] = PatternStat(n=len(items), hit_rate=h, nuke_rate=nk, mean_score=m)
    return EvalReport(n_decisions=n_decisions, n_no_trade=n_no_trade,
                      n_candidates=n_real, horizon=horizon, hit_rate=hit,
                      nuke_rate=nuke, mean_score=mean, mean_excess=excess,
                      n_unfillable=n_unfillable, n_missing=n_missing, fill_rate=fill_rate,
                      mean_score_all_in=all_in, by_pattern=by_pattern)
