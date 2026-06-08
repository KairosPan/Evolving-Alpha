# scripts/smoke_compare.py
"""手动冒烟:真实数据三方度量对比 HCH(自精炼内环) vs Hexpert(冻结种子 H) vs Hmin(裸基线)。

Run: DEEPSEEK_API_KEY=... python scripts/smoke_compare.py 20240601 20240607 [horizon]

需要:openai 已装、网络、akshare 可拉数、seeds/ 在位、DEEPSEEK_API_KEY。
先跑 scripts/smoke_akshare.py 核真实列名、scripts/smoke_deepseek_agent.py 验单日 agent,再跑本脚本。

成本提示:小窗口(3–5 交易日)起步。DeepSeek 调用 ≈ HCH(N 次 agent + 每 refine 3 次 p/K/M)+ Hexpert(N 次 agent);
akshare ≈ 3×N(已 memoize:四路共享同一真实数据,公平性硬保证 + 砍重复取数)。

⚠ 这是真实"自进化是否胜 frozen"的见真章脚本:读 hch_beats_hexpert + HCH−Hexpert delta。
单窗口、单次 LLM 采样,结论是信号不是定论;多窗口/多 episode 聚合见 1b-3b 债务。
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date as Date, datetime
from pathlib import Path

import pandas as pd

from youzi.data.source import AkshareSource
from youzi.harness.loader import load_seeds
from youzi.harness.snapshot import SnapshotStore
from youzi.llm.client import DeepSeekClient
from youzi.loop.compare import compare_harnesses
from youzi.loop.inner_loop import LoopConfig


class _MemoizedSource:
    """包装 MarketDataSource,记忆 trading_calendar 与每个 (池, 日) 取数。

    四路(HCH/Hexpert/Hmin_hb/Hmin_nt)各自重建引擎会重复拉同一天——memoize 让它们共享
    完全相同的真实数据(公平对比的硬保证)并把 akshare 调用砍 ~4×。
    防火墙不受影响:ReplayEngine 在本对象外层套 GuardedSource,guard.check(day) 仍先于取数。
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self._cal: list[Date] | None = None
        self._pools: dict[tuple[str, Date], pd.DataFrame] = {}

    def trading_calendar(self) -> list[Date]:
        if self._cal is None:
            self._cal = self._inner.trading_calendar()
        return self._cal

    def _pool(self, kind: str, fn, day: Date) -> pd.DataFrame:
        key = (kind, day)
        if key not in self._pools:
            self._pools[key] = fn(day)
        return self._pools[key]

    def zt_pool(self, day: Date) -> pd.DataFrame:
        return self._pool("zt", self._inner.zt_pool, day)

    def zt_pool_previous(self, day: Date) -> pd.DataFrame:
        return self._pool("prev", self._inner.zt_pool_previous, day)

    def zt_pool_blowup(self, day: Date) -> pd.DataFrame:
        return self._pool("blowup", self._inner.zt_pool_blowup, day)

    def dt_pool(self, day: Date) -> pd.DataFrame:
        return self._pool("dt", self._inner.dt_pool, day)


def _fmt_arm(name: str, arm) -> str:
    r = arm.report
    line = (f"  {name:<14} 决策={r.n_decisions:<3} 空仓={r.n_no_trade:<3} 候选={r.n_candidates:<3} "
            f"命中率={r.hit_rate:+.3f} 被砸率={r.nuke_rate:.3f} 期望分={r.mean_score:+.4f}")
    if arm.n_refines is not None:
        line += f"  [refine={arm.n_refines} 熔断={arm.n_breaker_trips} 冻结起={arm.frozen_from or '-'}]"
    return line


def main(start_ymd: str, end_ymd: str, horizon: int = 1, temperature: float = 0.3,
         scorer_kind: str = "pool") -> None:
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("缺少 DEEPSEEK_API_KEY(export 或 inline 传入)。"); sys.exit(1)
    start = datetime.strptime(start_ymd, "%Y%m%d").date()
    end = datetime.strptime(end_ymd, "%Y%m%d").date()
    seeds = Path(__file__).resolve().parent.parent / "seeds"
    tmp = tempfile.mkdtemp(prefix="youzi_compare_")

    from youzi.eval.scorer import PoolScorer, ReturnScorer
    scorer = ReturnScorer() if scorer_kind == "return" else PoolScorer()

    src = _MemoizedSource(AkshareSource())
    n_days = sum(1 for d in src.trading_calendar() if start <= d <= end)
    print(f"区间 {start}~{end} 内交易日 {n_days} 个,horizon={horizon},temperature={temperature},"
          f"scorer={scorer_kind}(return 模式下期望分读作平均收益)。"
          f"\n预计 DeepSeek 调用 ≈ HCH({n_days} agent + ~{max(0, n_days - horizon) * 3} refiner) "
          f"+ Hexpert({n_days} agent)。开始(慢且花钱)…\n")

    rep = compare_harnesses(
        lambda: load_seeds(seeds), src, start, end,
        agent_llm_factory=lambda: DeepSeekClient(temperature=temperature),
        refiner_llm_factory=lambda: DeepSeekClient(temperature=temperature),
        store_factory=lambda: SnapshotStore(Path(tmp)),
        loop_config=LoopConfig(horizon=horizon),
        scorer=scorer,
    )

    print("=== 三方度量对比(同窗同 oracle)===")
    for name in ("HCH", "Hexpert", "Hmin_highest", "Hmin_notrade"):
        print(_fmt_arm(name, rep.arms[name]))
    print("\n=== HCH − Hexpert ===")
    print(f"  Δ期望分={rep.hch_minus_hexpert_mean_score:+.4f}  "
          f"Δ命中率={rep.hch_minus_hexpert_hit_rate:+.4f}  "
          f"Δ被砸率={rep.hch_minus_hexpert_nuke_rate:+.4f}")
    verdict = "✅ HCH 胜 frozen" if rep.hch_beats_hexpert else "❌ HCH 未胜 frozen(持平或退化)"
    print(f"  verdict: {verdict}")

    # HCH 自进化到底改了啥(诊断:看 refine 每次的 applied/rejected 编辑)
    lr = rep.hch_loop_report
    if lr is not None:
        print("\n=== HCH 自进化轨迹(每次 refine 改了什么)===")
        if not lr.refine_events:
            print("  (无 refine)")
        for ev in lr.refine_events:
            r = ev.report
            print(f"  [{ev.date} ckpt={ev.checkpoint_version}] applied={len(r.applied)} rejected={len(r.rejected)}")
            for e in r.applied:
                print(f"      ✓ {e.pass_kind}:{e.tool} → {e.target_id}  «{e.rationale}»")
            for e in r.rejected:
                print(f"      ✗ {e.pass_kind}:{e.tool} → {e.target_id}  拒因:{e.reason}")
            for n in r.notes:
                print(f"      · {n}")
        for be in lr.breaker_events:
            print(f"  [熔断 {be.date}] {be.reason} rolling={be.rolling:+.3f} baseline={be.baseline} "
                  f"→ rollback={be.rolled_back_to}")
    print("\n⚠ 单窗口单次采样=信号非定论;多窗口/多 episode 聚合见 1b-3b 债务。")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: DEEPSEEK_API_KEY=... python scripts/smoke_compare.py <start_ymd> <end_ymd> [horizon] [temperature] [scorer:pool|return]")
        print("例:  DEEPSEEK_API_KEY=sk-... python scripts/smoke_compare.py 20240601 20240607 2 0.0 return")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2],
         int(sys.argv[3]) if len(sys.argv) > 3 else 1,
         float(sys.argv[4]) if len(sys.argv) > 4 else 0.3,
         sys.argv[5] if len(sys.argv) > 5 else "pool")
