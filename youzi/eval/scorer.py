# youzi/eval/scorer.py
from __future__ import annotations

from datetime import date as Date
from typing import Protocol

import pandas as pd

from youzi.eval.decision import DecisionPackage
from youzi.eval.fill import CostModel, fill_check
from youzi.eval.metrics import ScoredCandidate
from youzi.eval.oracle import SCORE, DayMembership, Outcome, outcome, path_outcome


def _close_on(ohlcv: pd.DataFrame, day: Date) -> float | None:
    """某交易日收盘价;缺行/缺值/≤0 → None。"""
    if ohlcv is None or ohlcv.empty or "date" not in ohlcv.columns:
        return None
    r = ohlcv.loc[ohlcv["date"] == day]
    if r.empty:
        return None
    cl = r.iloc[0].get("close")
    if cl is None or pd.isna(cl) or cl <= 0:
        return None
    return float(cl)


def _open_valid_row(ohlcv: pd.DataFrame, day: Date):
    """某交易日 OHLCV 行;缺行/open 缺/≤0 → None。"""
    if ohlcv is None or ohlcv.empty or "date" not in ohlcv.columns:
        return None
    r = ohlcv.loc[ohlcv["date"] == day]
    if r.empty:
        return None
    row = r.iloc[0]
    op = row.get("open")
    if op is None or pd.isna(op) or op <= 0:
        return None
    return row


class Scorer(Protocol):
    """把一步成熟决策打分成 code→ScoredCandidate(去重;可丢弃缺数候选)。

    mems=持有路径 entry..exit 逐日池成员(由 PoolRecord 取,长度=horizon);
    池制(PoolScorer)只看终点 mems[-1](=现行 exit 日语义);收益制(ReturnScorer)
    可吃整条路径做 stop-on-nuke。decision_mem=决策日(≤t)池成员,只用于按日基线
    day_baseline 的集合定义。一律事后消费 t+ 标签,不引入决策路径(防火墙)。
    空池日约定:decision_mem 为 None 或 limit_up 为空 → day_baseline=None,
    advantage 回退=score(显式回退,不臆造 0 基线)。
    """
    def score_step(self, decision: DecisionPackage, mems: list[DayMembership],
                   entry_day: Date, exit_day: Date, source,
                   decision_mem: DayMembership | None = None) -> dict[str, ScoredCandidate]: ...


class PoolScorer:
    """默认:池成员制 outcome + SCORE[outcome](= 现行为)。entry/exit/source 忽略。

    day_baseline=决策日 limit_up 池**全体成员**按 exit 日成员判 outcome 的 SCORE 均值
    (="闭眼买整个涨停池"的同日期望;PoolRecord 已录两日成员,零额外取数)。
    按 (决策日成员, exit 日成员) 缓存——同日跨臂复用免重算(DayMembership frozen 可哈希)。
    """

    def __init__(self) -> None:
        self._baseline_cache: dict[tuple[DayMembership, DayMembership], float | None] = {}

    def _day_baseline(self, decision_mem: DayMembership | None,
                      mem: DayMembership) -> float | None:
        if decision_mem is None or not decision_mem.limit_up:
            return None                               # 空池日:无基线(advantage 回退=score)
        key = (decision_mem, mem)
        if key not in self._baseline_cache:
            pool = decision_mem.limit_up
            self._baseline_cache[key] = sum(SCORE[outcome(c, mem)] for c in pool) / len(pool)
        return self._baseline_cache[key]

    def score_step(self, decision: DecisionPackage, mems: list[DayMembership],
                   entry_day: Date, exit_day: Date, source,
                   decision_mem: DayMembership | None = None) -> dict[str, ScoredCandidate]:
        mem = mems[-1]                                # 池制只看终点(exit 日),保持现行为
        base = self._day_baseline(decision_mem, mem)
        seen: set[str] = set()
        out: dict[str, ScoredCandidate] = {}
        for c in decision.candidates:
            if c.code in seen:
                continue
            seen.add(c.code)
            oc = outcome(c.code, mem)
            score = SCORE[oc]
            out[c.code] = ScoredCandidate(decision_date=decision.date, code=c.code,
                                          pattern=c.pattern, outcome=oc, score=score,
                                          day_baseline=base,
                                          advantage=score - base if base is not None else score)
        return out


class ReturnScorer:
    """C3 可成交收益尺:T+1 合规 + 一字板成交判定 + 成本 + 路径 stop-on-nuke + unfillable/missing 一等公民。

    每候选:次日(entry)按 fill_check 成交(一字板买不进→unfillable;无 OHLCV→missing,
    均不丢弃、score=0、不参与 mean 由 metrics 按 outcome 过滤);可成交则净收益=
    (settle 收盘−成交价)/成交价 − CostModel 往返成本。outcome 走 path_outcome(扫
    entry..exit 逐日,stop-on-nuke;首个 nuked 日==entry 则 T+1 顺延下一交易日 close)。
    day_baseline=决策日 limit_up 池**可成交+有数**成员的净收益均值(与候选同口径,
    cost 在 advantage 中抵消);按 (池成员, decision_date, entry, exit) 缓存,
    同一 scorer 实例假定同一数据源(compare 四臂同源)。
    """

    def __init__(self, cost_model: CostModel | None = None) -> None:
        self._cost = cost_model or CostModel()
        self._baseline_cache: dict[tuple, float | None] = {}
        self._calendar: list[Date] | None = None

    def _path_dates(self, source, entry_day: Date, exit_day: Date) -> list[Date]:
        """持有路径交易日(entry..exit,含端点);与 mems 同序对齐(均源自交易日历)。"""
        if self._calendar is None:
            self._calendar = sorted(source.trading_calendar())
        return [d for d in self._calendar if entry_day <= d <= exit_day]

    def _entry_names(self, source, entry_day: Date) -> dict[str, str]:
        """入场日 zt_pool 的 code→name(revision 6:候选 name 为空时回退取名做 ST 涨停幅判定)。
        取名失败/无 name 列 → 空 dict(退化为非 ST 近似,fill_check 标 name_missing)。"""
        try:
            df = source.zt_pool(entry_day)
        except Exception:                                 # noqa: BLE001 — 取名非关键,失败即退化
            return {}
        if df is None or getattr(df, "empty", True) or "code" not in df.columns or "name" not in df.columns:
            return {}
        return {str(c): ("" if pd.isna(n) else str(n)) for c, n in zip(df["code"], df["name"])}

    def _settle_one(self, code: str, name: str, mems: list[DayMembership],
                    decision_date: Date, entry_day: Date, exit_day: Date,
                    path_dates: list[Date], source) -> tuple[str, float | None, "Outcome | None", str]:
        """单候选结算 → (status, net, outcome, settle)。
        status∈{scored, unfillable, missing};net/outcome 仅 scored 非 None。
        """
        ohlcv = source.daily_ohlcv(code, decision_date, exit_day)  # decision_date 行作 prev_close
        prev_close = _close_on(ohlcv, decision_date)
        entry_row = _open_valid_row(ohlcv, entry_day)
        if prev_close is None or entry_row is None:
            return ("missing", None, None, "")
        fr = fill_check(entry_row, prev_close, code, name)
        if not fr.fillable:
            return ("unfillable", None, None, "")
        po = path_outcome(code, mems)
        if po.nuke_index is not None:
            # stop-on-nuke。path_dates 与 mems 同序等长(score_step 已 assert)+ horizon>=2 →
            # path_dates[1] 与 path_dates[ni] 必存在:ni==0(入场日即 nuke)按 T+1 顺延次日 close,否则该日 close。
            settle_date = path_dates[1] if po.nuke_index == 0 else path_dates[po.nuke_index]
            settle = "stop_on_nuke"
        else:
            settle_date = exit_day
            settle = "normal"
        exit_close = _close_on(ohlcv, settle_date)
        if exit_close is None:                        # 结算日停牌/缺数 → 诚实 missing
            return ("missing", None, None, "")
        net = (exit_close - fr.fill_price) / fr.fill_price - self._cost.round_trip_cost()
        return ("scored", net, po.outcome, settle)

    def _day_baseline(self, decision_mem: DayMembership | None, mems: list[DayMembership],
                      decision_date: Date, entry_day: Date, exit_day: Date,
                      path_dates: list[Date], source, names: dict[str, str]) -> float | None:
        if decision_mem is None or not decision_mem.limit_up:
            return None                               # 空池日:无基线(advantage 回退=score)
        # 缓存键含 mems(持有路径决定 path_outcome)→ 同窗跨臂复用且不因 mems 不同而串味
        key = (decision_mem.limit_up, decision_date, entry_day, exit_day, tuple(mems))
        if key not in self._baseline_cache:
            nets: list[float] = []
            for code in sorted(decision_mem.limit_up):   # 池成员 name 同走入场日 zt_pool 回退(ST 判定一致)
                status, net, _, _ = self._settle_one(code, names.get(code, ""), mems, decision_date,
                                                      entry_day, exit_day, path_dates, source)
                if status == "scored":
                    nets.append(net)                  # type: ignore[arg-type]
            self._baseline_cache[key] = sum(nets) / len(nets) if nets else None
        return self._baseline_cache[key]

    def score_step(self, decision: DecisionPackage, mems: list[DayMembership],
                   entry_day: Date, exit_day: Date, source,
                   decision_mem: DayMembership | None = None) -> dict[str, ScoredCandidate]:
        if entry_day >= exit_day:                     # T+1 守门(revision 4):同日买卖非法
            raise ValueError(
                f"ReturnScorer 要求 horizon>=2(T+1 合规):entry_day({entry_day}) 必须早于 exit_day({exit_day})")
        path_dates = self._path_dates(source, entry_day, exit_day)
        # 不变量:持有路径逐日成员 mems 与交易日历切片 path_dates 同序等长——错位即数据/日历异常,loud
        assert len(path_dates) == len(mems), \
            f"path_dates({len(path_dates)}) 与 mems({len(mems)}) 长度不一致:交易日历/持有路径错位"
        names = self._entry_names(source, entry_day)   # revision 6:候选 name 为空时的回退名源
        base = self._day_baseline(decision_mem, mems, decision.date,
                                  entry_day, exit_day, path_dates, source, names)
        seen: set[str] = set()
        out: dict[str, ScoredCandidate] = {}
        for c in decision.candidates:
            if c.code in seen:
                continue
            seen.add(c.code)
            status, net, oc, settle = self._settle_one(
                c.code, c.name or names.get(c.code, ""), mems, decision.date,
                entry_day, exit_day, path_dates, source)
            if status == "scored":
                adv = net - base if base is not None else net
                out[c.code] = ScoredCandidate(decision_date=decision.date, code=c.code,
                                              pattern=c.pattern, outcome=oc, score=net,
                                              day_baseline=base, advantage=adv, settle=settle)
            else:                                     # unfillable / missing:一等公民,不丢弃,不参与 mean
                out[c.code] = ScoredCandidate(decision_date=decision.date, code=c.code,
                                              pattern=c.pattern, outcome=status, score=0.0,
                                              day_baseline=base, advantage=0.0, settle="")
        return out
