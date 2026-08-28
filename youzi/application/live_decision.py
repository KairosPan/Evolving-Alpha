# youzi/application/live_decision.py
"""LiveDecisionService —— live 决策链的薄编排。

    MarketSnapshot(冻结) → StrategyRunner(H + Agent) → (+ 冻结 AccountSnapshot)
        → LLM Agent → DecisionDraft(AgentRun) → 确定性校验 + 人工确认
        → Decision / Fill / Position

三条不可让的纪律:

1. **防火墙**:所有取数经 `GuardedSource(AsOfGuard(trade_date))`;Agent 只拿
   `MarketState` / `CandidateUniverse` 这类**冻结对象**,不持有 source 或 DB 句柄
   (构造方式对齐 `youzi/eval/walk_forward.py`)。
2. **冻结账户**:`run()` 把账户折叠成 `account_context_json` 写进 AgentRun,
   `adopt()` 的一切校验**只读这份 JSON**,不再回查活账户——建议与校验看到的
   是同一个世界。
3. **只建议不下单**:`adopt()` 产出的是待人确认的建议单;`decision` 由人写,
   `fill` 由人回报。系统全程不碰券商接口。

`adopt()` 的可成交性标注**只用 ≤t 数据**(`limit_threshold` + t 日收盘参考价,
在 `run()` 时就随候选冻结),**不取 t+1 OHLCV**。`youzi/eval/fill.py` 的
`fill_check` 需要入场日 OHLCV,那是回测尺子的位置;把它搬进实盘路径等于
把未来函数引进决策链。此处复用的是它的**判定思路**(比值定涨停、一字买不进),
不是它的未来数据。
"""
from __future__ import annotations

import hashlib
from datetime import date as Date, datetime as DateTime, time as Time
from pathlib import Path

from youzi.agent.agent import LLMAgentPolicy
from youzi.data.source import GuardedSource
from youzi.eval.fill import limit_threshold
from youzi.features.builder import build_market_state
from youzi.harness.loader import load_seeds
from youzi.replay.firewall import AsOfGuard
from youzi.schemas.market import MarketState
from youzi.store.account_repo import AccountRepo, AccountView, Fill
from youzi.store.agent_run_repo import AgentRun, AgentRunRepository
from youzi.store.errors import IllegalTransitionError
from youzi.store.ops_repo import Decision, OpsRepository, OpsSession
from youzi.universe.universe import build_universe

SEED_VERSION = "seed"
_SNAPSHOT_PREFIX = "snapshot:"
LOT = 100                     # A 股最小交易单位:一手 = 100 股
CLOSE_TIME = Time(15, 0)      # 收盘快照时点(与 ReplayEngine 一致)


def min_lot(code: str) -> int:
    """最小申报数量:科创板(68 开头)200 股起,其余板块一手 100 股。

    与 `limit_threshold` 同理按 code 前缀分板块——用统一的 100 会把
    688 候选的最低资金占用低估一半,资金校验假 ok。
    """
    return 200 if str(code).startswith("68") else LOT


class StrategyNotFoundError(ValueError):
    """请求了不存在的策略版本 → web 层映射 422。"""


class _RecordingLLM:
    """透明包住注入的 LLMClient,截留最后一次 (system, user, raw) 供审计落库。

    包装而非改 `LLMAgentPolicy`:领域层零改动纪律,web/应用层的审计需求不得
    渗回 `youzi/agent/`。异常路径下 raw 为 None,但指纹已记(提示可复现)。
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.system: str = ""
        self.user: str = ""
        self.raw: str | None = None
        self.fingerprint: str = ""

    def complete(self, system: str, user: str) -> str:
        self.system, self.user = system, user
        self.fingerprint = hashlib.sha256(
            f"{system}\x00{user}".encode("utf-8")).hexdigest()[:16]
        self.raw = self._inner.complete(system, user)
        return self.raw


def _account_context(view: AccountView, frozen_at: str) -> dict:
    """AccountView → 冻结进 AgentRun 的账户上下文 JSON 结构。

    `frozen_at` 是**冻结这一刻的墙钟**,不是交易日收盘戳:账户折叠的时间轴是
    "成交何时被登记"(fills.created_at),与行情的 as_of 是两条独立时间轴,
    混用会把补录的历史成交从上下文里悄悄漏掉。
    """
    return {
        "account_id": view.account_id,
        "as_of": frozen_at,
        "cash": view.cash,
        "is_absolute_cash": view.is_absolute_cash,
        "positions": {p.code: {"qty": p.qty, "avg_cost": p.avg_cost} for p in view.positions},
        "realized_pnl": view.realized_pnl,
        "n_fills": view.n_fills,
        "baseline_as_of": view.baseline_as_of,
        "baseline_source": view.baseline_source,
        "anomalies": list(view.anomalies),
    }


def check_candidate(entry: dict, account_ctx: dict) -> dict:
    """确定性校验:对一个候选做**纯函数**判定(只吃冻结数据,不取数、不看未来)。

    子项各自判定,总状态取最坏(blocked > unknown > ok):
      · pricing —— 有 t 日收盘参考价才谈得上定价;缺 → unknown;
      · cash —— 绝对现金够买一手(按 t+1 涨停价的最坏情形)才 ok;不够 → blocked;
        账户无基线快照(现金只是净变动)→ unknown,**不冒充通过**;
      · position —— 已持仓只提示(加仓是合法动作),不拦;
      · fill_risk —— t 日封住涨停 → 提示次日一字买不进的风险(不拦,人决定)。

    校验不过的候选由 `adopt()` **标记保留**(check_status='blocked'),绝不静默丢弃。
    """
    reasons: list[str] = []
    checks: dict[str, str] = {}
    close = entry.get("close")
    limit_pct = entry.get("limit_pct")
    if limit_pct is None:
        limit_pct = limit_threshold(str(entry.get("code", "")), str(entry.get("name") or ""))

    lot = min_lot(str(entry.get("code", "")))
    out: dict = {"limit_pct": limit_pct, "ref_price": close, "lot_size": lot}

    # 1) 定价
    if close is None or close <= 0:
        checks["pricing"] = "unknown"
        reasons.append("缺 t 日收盘价,无法定价校验")
        limit_price = None
        lot_cost = None
    else:
        checks["pricing"] = "ok"
        limit_price = round(close * (1.0 + limit_pct), 4)
        lot_cost = round(limit_price * lot, 2)
    out["limit_price_next"] = limit_price       # t+1 涨停价(最坏成交价)
    out["lot_cost"] = lot_cost                  # 按最小申报数量的最坏资金占用

    # 2) 资金
    cash = account_ctx.get("cash")
    if not account_ctx.get("is_absolute_cash"):
        checks["cash"] = "unknown"
        reasons.append("账户无基线快照,现金为净变动口径,资金校验跳过")
    elif lot_cost is None or cash is None:
        checks["cash"] = "unknown"
    elif cash < lot_cost:
        checks["cash"] = "blocked"
        reasons.append(
            f"现金 {cash:.2f} 不足以按涨停价买入最小申报数量 {lot} 股({lot_cost:.2f})")
    else:
        checks["cash"] = "ok"

    # 3) 已持仓(提示,不拦)
    held = (account_ctx.get("positions") or {}).get(str(entry.get("code", "")))
    if held:
        checks["position"] = "ok"
        reasons.append(f"已持仓 {held.get('qty')} 股,本次为加仓")
    else:
        checks["position"] = "ok"

    # 4) 可成交性风险(提示,不拦)
    checks["fill_risk"] = "ok"
    if entry.get("status") == "limit_up":
        out["one_word_risk"] = True
        reasons.append(
            "t 日封涨停:次日若一字开板则买不进"
            + (f"(涨停参考价 {limit_price})" if limit_price is not None else ""))
    else:
        out["one_word_risk"] = False

    if "blocked" in checks.values():
        status = "blocked"
    elif "unknown" in checks.values():
        status = "unknown"
    else:
        status = "ok"
    out["checks"] = checks
    out["reasons"] = reasons
    out["status"] = status
    return out


class LiveDecisionService:
    """live 决策编排。全部依赖构造注入 → 离线(FakeSource + MockLLM)可完整测。"""

    def __init__(self, *, source, llm, agent_runs: AgentRunRepository,
                 accounts: AccountRepo, ops: OpsRepository,
                 seeds_dir: str | Path | None = None, snapshot_store=None,
                 strategy_id: str = "llm_agent", model: str = "",
                 temperature: float | None = None) -> None:
        self._source = source
        self._llm = llm
        self._runs = agent_runs
        self._accounts = accounts
        self._ops = ops
        self._seeds_dir = Path(seeds_dir) if seeds_dir else _default_seeds_dir()
        self._snapshot_store = snapshot_store
        self._strategy_id = strategy_id
        self._model = model
        self._temperature = temperature

    # ── 只读查询 ──────────────────────────────────────────────────────────
    def list_strategies(self) -> list[dict]:
        """可用的 H 版本:种子 + 已存快照。`version` 即 `run()` 的 strategy_version。"""
        out = [{"version": SEED_VERSION, "kind": "seed",
                "label": f"种子 H({self._seeds_dir.name}/)",
                "available": self._seeds_dir.is_dir()}]
        if self._snapshot_store is not None:
            for v in self._snapshot_store.list_versions():
                out.append({"version": f"{_SNAPSHOT_PREFIX}{v}", "kind": "snapshot",
                            "label": f"Harness 快照 v{v}", "available": True})
        return out

    def market_snapshot(self, trade_date: Date) -> dict:
        """某交易日的冻结市场事实(经防火墙)。web 只读展示用。"""
        guarded = self._guarded(trade_date)
        state = self._observe(trade_date, guarded)
        universe = build_universe(guarded, trade_date)
        return {
            "date": trade_date.isoformat(),
            "as_of": state.as_of.isoformat(),
            "state": state.model_dump(mode="json"),
            "universe": {
                "n": len(universe),
                "limit_up": len(universe.by_status("limit_up")),
                "blowup": len(universe.by_status("blowup")),
                "limit_down": len(universe.by_status("limit_down")),
                "stocks": [s.model_dump(mode="json") for s in universe.all()],
            },
        }

    def account_view(self, account_id: str, *, as_of: str | None = None) -> AccountView:
        """账户折叠视图(持仓/现金永远是 fills 的查询函数)。"""
        return self._accounts.fold(account_id, as_of=as_of)

    def get_run(self, run_id: str) -> AgentRun:
        return self._runs.require(run_id)

    def list_runs(self, trade_date: Date) -> list[AgentRun]:
        return self._runs.list_by_date(trade_date)

    def get_session(self, session_id: str) -> OpsSession:
        return self._ops.require_session(session_id)

    # ── 用例 ─────────────────────────────────────────────────────────────
    def run(self, trade_date: Date, strategy_version: str, account_id: str) -> AgentRun:
        """跑一次建议:冻结市场 + 冻结账户 → LLM → 落 AgentRun。

        `strategy_version` 非法 → `StrategyNotFoundError`(**在建 run 之前**抛,
        参数错不该污染运行历史)。之后的任何失败(取数 / LLM / 解析)都落成
        **failed 的 AgentRun** 并返回,不裸抛——实盘链路上"没有记录的失败"最危险。
        """
        harness, harness_ref = self._load_harness(strategy_version)   # 先校验参数

        guarded = self._guarded(trade_date)
        as_of = DateTime.combine(trade_date, CLOSE_TIME)     # 行情时间轴(≤t 防火墙)
        frozen_at = DateTime.now().isoformat(timespec="microseconds")  # 账务时间轴
        account_view = self._accounts.fold(account_id)       # 折叠到此刻 = live 语义
        account_ctx = _account_context(account_view, frozen_at)
        # 决策时刻的账户冻结副本落库(审计;source='frozen' → 不参与折叠基线选取)
        self._accounts.put_snapshot(
            account_id=account_id, as_of=frozen_at, cash=account_view.cash,
            positions={p.code: p.qty for p in account_view.positions}, source="frozen")

        run = self._runs.create(
            trade_date=trade_date, strategy_id=self._strategy_id,
            market_as_of=as_of.isoformat(),
            snapshot_ref=f"{type(self._source).__name__}@{trade_date.isoformat()}",
            harness_snapshot_ref=harness_ref, account_id=account_id,
            account_context=account_ctx, model=self._model, temperature=self._temperature)
        self._runs.mark_running(run.run_id)

        recorder = _RecordingLLM(self._llm)
        try:
            state = self._observe(trade_date, guarded)
            universe = build_universe(guarded, trade_date)
            # 防火墙:agent 只拿冻结的 state/universe,不持有 source 或仓储句柄
            agent = LLMAgentPolicy(harness, recorder)
            pkg = agent.decide(state, universe)
            entries = {c.code: self._entry_context(c, universe, guarded, trade_date)
                       for c in pkg.candidates}
        except Exception as e:                       # noqa: BLE001 — 任何失败都要留痕
            return self._runs.mark_failed(
                run.run_id, error=f"{type(e).__name__}: {e}", raw_output=recorder.raw)

        if recorder.fingerprint:
            self._runs.set_prompt_fingerprint(run.run_id, recorder.fingerprint)
        return self._runs.mark_succeeded(
            run.run_id, raw_output=recorder.raw or "",
            parsed_output={"decision": pkg.model_dump(mode="json"), "entries": entries})

    def adopt(self, agent_run_id: str) -> OpsSession:
        """采纳一次运行 → 建议单(ops_session + ops_candidate)。

        **仅接受 status='succeeded'**;重复采纳 / 同账户同日已有建议单 → 抛错给调用方
        (`IllegalTransitionError` / `DuplicateError`),绝不静默覆盖。
        校验不过的候选写 `check_status='blocked'` **保留在单上**,人看得见系统为何否掉。
        """
        run = self._runs.require(agent_run_id)
        if run.status != "succeeded":
            raise IllegalTransitionError(
                f"仅 succeeded 运行可采纳,当前 status={run.status}(run_id={agent_run_id})")
        if run.adopted_at is not None:
            raise IllegalTransitionError(f"运行已采纳过: {agent_run_id} @ {run.adopted_at}")

        parsed = run.parsed_output()
        decision = parsed.get("decision") or {}
        entries = parsed.get("entries") or {}
        account_ctx = run.account_context()          # 纪律 2:校验只读这份冻结 JSON
        harness = self._try_load_harness(run.harness_snapshot_ref)

        rows: list[dict] = []
        for c in (decision.get("candidates") or []):
            code = str(c.get("code") or "")
            entry = dict(entries.get(code) or {})
            entry.setdefault("code", code)
            entry.setdefault("name", c.get("name") or "")
            chk = check_candidate(entry, account_ctx)
            rows.append({
                "code": code, "name": str(c.get("name") or ""),
                "pattern": str(c.get("pattern") or ""),
                "score": c.get("confidence"), "reason": str(c.get("reason") or ""),
                "plan": _plan_for(c.get("pattern"), harness),
                "check_status": chk["status"], "check": chk,
            })
        return self._ops.adopt_run(run_id=run.run_id, account_id=run.account_id,
                                   trade_date=run.trade_date, candidates=rows)

    def confirm(self, candidate_id: str, action: str, note: str = "") -> Decision:
        """人工确认一个候选(buy/skip/watch)。系统不代人确认。"""
        return self._ops.confirm(candidate_id=candidate_id, action=action, note=note)

    def record_fill(self, *, operation_id: str, account_id: str, trade_date: Date,
                    code: str, side: str, price: float, qty: int, fee: float = 0.0,
                    decision_id: str | None = None) -> tuple[Fill, bool]:
        """回报一笔成交(转发 AccountRepo,以 operation_id 幂等)。"""
        return self._accounts.record_fill(
            operation_id=operation_id, account_id=account_id, trade_date=trade_date,
            code=code, side=side, price=price, qty=qty, fee=fee, decision_id=decision_id)

    # ── 内部 ─────────────────────────────────────────────────────────────
    def _guarded(self, day: Date) -> GuardedSource:
        return GuardedSource(self._source, AsOfGuard(day))

    def _observe(self, day: Date, guarded: GuardedSource) -> MarketState:
        """当日冻结市场状态。

        债务:`history=[]` → `sentiment_norm` 恒为 None(样本不足即诚实为 None,
        不臆造)。live 侧要拿到 regime-relative 归一,需先回灌历史 sentiment_raw
        序列(自然落点是 PITStore),留作后续。
        """
        return build_market_state(day, guarded, [],
                                  as_of=DateTime.combine(day, CLOSE_TIME))

    def _entry_context(self, cand, universe, guarded, day: Date) -> dict:
        """把候选的 ≤t 入场事实冻结进 AgentRun:adopt() 之后就是纯离线函数。"""
        snap = universe.get(cand.code)
        name = cand.name or (snap.name if snap else "")
        ctx: dict = {
            "code": cand.code, "name": name,
            "status": snap.status if snap else None,
            "boards": snap.boards if snap else None,
            "pct": snap.pct if snap else None,
            "seal_amount": snap.seal_amount if snap else None,
            "limit_pct": limit_threshold(cand.code, name),
            "close": None,
        }
        try:            # t 日收盘参考价;缺数(停牌/未捕获)→ None,校验降级为 unknown
            df = guarded.daily_ohlcv(cand.code, day, day)
            if df is not None and not df.empty and "close" in df.columns:
                ctx["close"] = float(df["close"].iloc[-1])
        except Exception:                # noqa: BLE001 — 单只取价失败不该毁掉整次运行
            ctx["close"] = None
        return ctx

    def _load_harness(self, strategy_version: str):
        """`strategy_version` → (HarnessState, harness_snapshot_ref)。

        `seed` = `seeds/` 种子;`snapshot:<N>` = SnapshotStore 第 N 版。其余 → 抛错。
        """
        v = (strategy_version or "").strip()
        if v in ("", SEED_VERSION):
            try:
                return load_seeds(self._seeds_dir), SEED_VERSION
            except (FileNotFoundError, ValueError) as e:
                raise StrategyNotFoundError(f"种子 H 载入失败: {e}") from e
        if v.startswith(_SNAPSHOT_PREFIX):
            if self._snapshot_store is None:
                raise StrategyNotFoundError("未配置 SnapshotStore,无法载入 H 快照")
            try:
                version = int(v[len(_SNAPSHOT_PREFIX):])
            except ValueError:
                raise StrategyNotFoundError(f"非法快照版本号: {strategy_version}") from None
            try:
                harness, _log = self._snapshot_store.load(version)
            except FileNotFoundError as e:
                raise StrategyNotFoundError(str(e)) from e
            return harness, v
        raise StrategyNotFoundError(f"未知策略版本: {strategy_version}")

    def _try_load_harness(self, ref: str | None):
        """adopt 时按 ref 复载 H(仅为把技能计划 join 上单子)。载不到 → None,降级。"""
        try:
            harness, _ = self._load_harness(ref or SEED_VERSION)
        except (StrategyNotFoundError, FileNotFoundError, RuntimeError, ValueError):
            return None
        return harness


def _plan_for(pattern, harness) -> dict | None:
    """候选 pattern → 技能的可执行计划(trigger/entry/exit_stop/taboo)。join 不到 → None。"""
    if harness is None or not pattern:
        return None
    from youzi.refine.credit import resolve_skill          # 局部导入,避免包级循环
    sk = resolve_skill(str(pattern), harness)
    if sk is None:
        return None
    return {"skill_id": sk.skill_id, "name_cn": sk.name_cn, "trigger": sk.trigger,
            "entry": sk.entry, "exit_stop": sk.exit_stop, "taboo": list(sk.taboo)}


def _default_seeds_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "seeds"


__all__ = ["LiveDecisionService", "StrategyNotFoundError", "check_candidate", "LOT",
           "min_lot"]
