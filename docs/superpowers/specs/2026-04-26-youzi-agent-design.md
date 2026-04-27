# 游资智能体 (youzi-agent) — 设计文档

**日期**: 2026-04-26
**规格来源**: `A股游资智能体_LangGraph设计.md`
**关联**: 复用 `2026-04-24-market-sentiment-analyzer-design.md` 中的 CycleTag/仓位思路（思想复用，代码不复用）

## 1. 目标与范围

构建一个 **EOD 批处理的多智能体系统**，复刻《轮回》中的"大周期 → 情绪周期 → 题材 → 龙头 → 模式匹配 → 候选池 → 风控 → 计划 → 复盘"流水线。

**v1 必交付**：
- LangGraph 父图 + 4 个子图（first_board / weak_to_strong / continuous / setback_reversal）的端到端跑通
- 数据：仅 akshare（日线 + 涨停板池 + 同花顺概念）
- LLM：DeepSeek，仅在 `theme_analyst` 必调 + `pattern_matcher` 边缘情况兜底
- 持久化：SQLite checkpointer（无向量记忆）
- 输出：每日生成 `runs/{date}/report.md` + `report.json`
- CLI：`python -m youzi_agent [date] [--no-llm] [--refresh] [--json]`

**v1 非目标**：
- 实时盘中 tick 驱动 / 集合竞价节点
- 财经新闻流（财联社）/ 龙虎榜 / 分时数据
- 向量记忆库 / 跨日相似性检索
- LeaderRelay / Capacity / Sunflower 等更高阶子 agent
- 真实下单 / 风控熔断 / 资金账户接入

## 2. 设计哲学

| 设计文档中的概念 | 本系统对应 |
|---|---|
| 大周期 / 情绪周期 | 父图 State 字段（`index_phase` / `emotion_phase`） |
| 葵花宝典 1234 | `pattern_matcher` 真值表 |
| 龙头接力 / 弱转强 / 反包 | 4 个子图 |
| 复盘 / 肌肉记忆 | `post_mortem` 节点 + SQLite checkpointer（v1 不做向量库） |
| 预期差 | v1 不实现（属于盘中节点） |

**架构选择 = Approach 2（父图 + 子图分层）**：
- 父图三段：SENSE → ANALYZE → DECIDE
- 4 个子图独立 `StateGraph`，通过 langgraph 子图原生支持挂入父图
- 父图条件路由用 `Send` API 把激活的子图并行 fan-out
- 子图返回的 `candidates` 由父图 `Annotated[list, add]` reducer 合并

**节点写作风格**：
- 默认纯规则（pure Python function）
- LLM 仅出现在 2 个节点，且必须有 `--no-llm` 时的规则 fallback
- 所有节点 `def node(state) -> dict`，返回 partial state，不 mutate

## 3. 项目结构

```
youzi_agent/
├── pyproject.toml
├── .env                              # DEEPSEEK_API_KEY (gitignore)
├── runs/                             # 每日 JSON + Markdown 报告归档
├── checkpoints.db                    # SQLite checkpointer (gitignore)
├── data_cache/                       # akshare parquet 缓存 (gitignore)
├── src/youzi_agent/
│   ├── __init__.py
│   ├── state.py                      # 全局 + 子图 TypedDict & reducer
│   ├── data/
│   │   ├── __init__.py
│   │   ├── akshare_client.py         # 所有 akshare 调用封装 + 重试 + 缓存
│   │   └── cache.py                  # 本地 parquet 缓存（按交易日）
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── deepseek.py               # langchain_openai 兼容客户端
│   │   └── schemas.py                # Pydantic 输出 schema
│   ├── nodes/
│   │   ├── market_sensor.py
│   │   ├── index_cycle.py
│   │   ├── emotion.py
│   │   ├── cycle_switch.py
│   │   ├── theme_analyst.py          # LLM
│   │   ├── leader_tracker.py
│   │   ├── pattern_matcher.py        # 真值表 + LLM 兜底
│   │   ├── arbitrage.py
│   │   ├── risk_guard.py
│   │   ├── trade_planner.py
│   │   └── post_mortem.py
│   ├── subagents/
│   │   ├── __init__.py
│   │   ├── weak_to_strong.py
│   │   ├── first_board.py
│   │   ├── continuous.py
│   │   └── setback_reversal.py
│   ├── graph.py                      # 父图组装
│   ├── reducers.py                   # 自定义 reducer（list 替换语义）
│   ├── reporting.py                  # JSON ↔ Markdown
│   └── cli.py
└── tests/
    ├── conftest.py
    ├── fixtures/
    ├── test_nodes/
    ├── test_subagents/
    ├── test_data/
    └── test_e2e.py
```

每个 Python 文件 < 250 行。包名 `youzi_agent`（"游资"拼音）。

## 4. State 模型

### 4.1 父图 `MarketState`

```python
from typing import TypedDict, Literal, Optional, Annotated
from operator import add

class ThemeProfile(TypedDict):
    name: str
    members: list[str]
    leader: Optional[str]
    catalysts: list[str]
    phase: Literal["budding","horizontal","vertical","switching","exhausted"]
    resonance_score: float

class LeaderProfile(TypedDict):
    code: str
    name: str
    consec_boards: int
    role: Literal["total","capacity","complement","companion"]
    sealed_amount: float
    blast_today: bool
    div_count: int

class PatternHit(TypedDict):
    pattern_id: str
    filter_desc: str
    target_subagent: str

class Candidate(TypedDict):
    code: str
    name: str
    pattern_id: str
    score: float
    reason: str
    suggested_position: float

class TradePlan(TypedDict):
    date: str
    position_total_max: float
    candidates: list[Candidate]
    avoid_list: list[str]
    notes: str

class MarketState(TypedDict, total=False):
    # ---- 入参 ----
    target_date: str
    use_llm: bool

    # ---- 数据层（不进 checkpoint）----
    raw: dict

    # ---- 大周期 / 指数 ----
    index_phase: Literal["uptrend","top","downtrend","bottom","oscillation"]
    sz_macd: dict
    cyb_macd: dict
    market_volume: float
    big_cap_volume_ratio: float

    # ---- 中周期 / 五日线 ----
    five_day_pos: Literal["above","top_horizontal","below","bottom_grinding"]
    money_effect: Literal["positive","neutral","negative"]
    is_new_cycle_day: bool
    is_only_rebound: bool

    # ---- 情绪 ----
    emotion_phase: Literal[
        "chaos","recovery","warming","main_rise",
        "climax","divergence","decay_1","decay_mid","decay_2"
    ]
    sentiment_value: int
    limit_up_count: int
    consec_top: int
    blast_rate: float

    # ---- 题材 + 龙头 ----
    themes: dict[str, ThemeProfile]
    main_theme: Optional[str]
    theme_axis: Literal["horizontal","vertical","switching","exhausted"]
    leader_stack: list[LeaderProfile]
    succession_status: Literal["healthy","first_div","second_div","broken","trans"]

    # ---- 模式 / 候选 / 决策 ----
    pattern_hits: Annotated[list[PatternHit], add]
    candidates: Annotated[list[Candidate], add]      # 子图并行写入,reducer 拼接
    final_candidates: list[Candidate]                 # RiskGuard 过滤后的结果（覆盖语义）
    arb_opportunities: Annotated[list[Candidate], add]
    risk_flags: Annotated[list[str], add]
    plan: Optional[TradePlan]

    # ---- 复盘 ----
    review: Optional[dict]

    # ---- 运行时 ----
    errors: Annotated[list[str], add]
```

> **关键决策**：`candidates` 字段用 `Annotated[list, add]` 让 4 个子图能并行写而不互相覆盖。RiskGuard 过滤需要"替换"语义，因此单独存到 `final_candidates`（不带 reducer，写即覆盖）。

### 4.2 子图切片 State

每个子图自定义一个 `TypedDict`，只包含它需要的字段；父图通过 `Send` 传切片。

```python
class FirstBoardState(TypedDict, total=False):
    target_date: str
    pattern_hits: list[PatternHit]
    raw: dict
    leader_stack: list[LeaderProfile]
    themes: dict[str, ThemeProfile]
    main_theme: Optional[str]
    candidates: Annotated[list[Candidate], add]
    errors: Annotated[list[str], add]
    # 子图私有字段（_ 前缀,不出子图）
```

其余 3 个子图（`WeakToStrongState` / `ContinuousState` / `SetbackReversalState`）结构相同，只是私有字段不同。

### 4.3 Checkpoint 排除大对象

`raw` 字段是 DataFrame 字典（几 MB），每节点都序列化到 SQLite 会爆。两种处理方案：

- **方案 A（v1 选）**：`raw` 在 `market_sensor` 装入 state 后，所有下游节点只读不写；`post_mortem` 在最后把 `raw` 弹出再 emit 完整 state。Checkpoint 仍包含 `raw`，但因为 SQLite saver 是按节点 patch 持久化，`raw` 只写入一次（market_sensor 那一步）。可接受。
- **方案 B（v2 优化）**：自定义 checkpointer 序列化器，跳过 `raw` 字段，需要回放时从 `data_cache/` 重建。

v1 用方案 A。

## 5. 父图拓扑

```
                       ┌─────────────────────────┐
                       │  STAGE A · SENSE        │
                       └────────┬────────────────┘
                                ▼
        market_sensor → index_cycle → emotion → cycle_switch
                                ▼
                       ┌─────────────────────────┐
                       │  STAGE B · ANALYZE      │
                       └────────┬────────────────┘
                                ▼
        theme_analyst (LLM) → leader_tracker → pattern_matcher (rule + LLM 兜底)
                                ▼
                       ┌─────────────────────────┐
                       │  STAGE C · DECIDE       │
                       └────────┬────────────────┘
                                ▼
        dispatch ──Send──▶  ┌─ weak_to_strong (子图)
                            ├─ first_board    (子图)
                            ├─ continuous     (子图)
                            └─ setback_reversal (子图)
        ──── join (reducer 合并) ────
                                ▼
        arbitrage → risk_guard → trade_planner → post_mortem → END
```

### 5.1 装配代码骨架

```python
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from langgraph.checkpoint.sqlite import SqliteSaver

def build_graph():
    g = StateGraph(MarketState)

    # STAGE A
    g.add_node("market_sensor", market_sensor_node)
    g.add_node("index_cycle",   index_cycle_node)
    g.add_node("emotion",       emotion_node)
    g.add_node("cycle_switch",  cycle_switch_node)
    g.add_edge(START, "market_sensor")
    g.add_edge("market_sensor", "index_cycle")
    g.add_edge("index_cycle",   "emotion")
    g.add_edge("emotion",       "cycle_switch")

    # STAGE B
    g.add_node("theme_analyst",   theme_analyst_node)
    g.add_node("leader_tracker",  leader_tracker_node)
    g.add_node("pattern_matcher", pattern_matcher_node)
    g.add_edge("cycle_switch",    "theme_analyst")
    g.add_edge("theme_analyst",   "leader_tracker")
    g.add_edge("leader_tracker",  "pattern_matcher")

    # STAGE C — 子图作为 callable node
    g.add_node("weak_to_strong",   build_w2s_subgraph())
    g.add_node("first_board",      build_fb_subgraph())
    g.add_node("continuous",       build_con_subgraph())
    g.add_node("setback_reversal", build_sr_subgraph())

    def dispatch(state: MarketState):
        active = {h["target_subagent"] for h in state.get("pattern_hits", [])}
        if not active:
            return ["join"]
        return [Send(name, _slice_for_subagent(state, name)) for name in active]

    g.add_conditional_edges(
        "pattern_matcher", dispatch,
        ["weak_to_strong","first_board","continuous","setback_reversal","join"],
    )

    g.add_node("join", lambda s: {})       # noop, 让 reducer 触发
    for sub in ["weak_to_strong","first_board","continuous","setback_reversal"]:
        g.add_edge(sub, "join")

    g.add_node("arbitrage",     arbitrage_node)
    g.add_node("risk_guard",    risk_guard_node)
    g.add_node("trade_planner", trade_planner_node)
    g.add_node("post_mortem",   post_mortem_node)
    g.add_edge("join",          "arbitrage")
    g.add_edge("arbitrage",     "risk_guard")
    g.add_edge("risk_guard",    "trade_planner")
    g.add_edge("trade_planner", "post_mortem")
    g.add_edge("post_mortem",   END)

    saver = SqliteSaver.from_conn_string("checkpoints.db")
    return g.compile(checkpointer=saver)
```

## 6. SENSE 阶段节点

### 6.1 `market_sensor_node`

调 `AkshareClient` 拉今日 / 昨日涨停池、炸板池、三大指数日线、市场活跃度，装入 `state["raw"]`，并算出基础统计：`limit_up_count` / `consec_top` / `blast_rate`。详见 § 11 数据层。

### 6.2 `index_cycle_node`

输入 `raw["idx_sh"]` / `raw["idx_cyb"]`，纯规则计算：
- `index_phase`：基于近 60 日均线斜率 + 当前价相对位置
  - 价格 > MA60 且 MA20 > MA60 上行 → `uptrend`
  - 价格 < MA60 且 MA20 < MA60 下行 → `downtrend`
  - MA60 横盘 ±2% → `oscillation`
  - 顶背离形态（用 MACD）→ `top`
  - 底背离形态 → `bottom`
- `sz_macd` / `cyb_macd`：日线 MACD（自实现，不引 talib，避免 C 依赖）
- `market_volume`：当日两市总成交（从 `raw["activity"]` 或日线推算）
- `big_cap_volume_ratio`：v1 不计算（akshare 没现成接口），赋默认 0.0

### 6.3 `emotion_node`

输入：`limit_up_count` / `consec_top` / `blast_rate` / `raw["activity"]`（如有 red_count）

判定逻辑（沿用 `market_sentiment` spec 的思路，但术语改为 `emotion_phase` 9 段）：

```python
def classify_emotion(red_count, ma5, ma3, ma5_turn, blast_rate, consec_top, lu_count):
    if red_count <= 1000:
        return "chaos"
    if red_count >= 4000 and lu_count > 100:
        return "climax"
    if ma5_turn == "turn_up":
        return "recovery" if ma5 < 2000 else "warming"
    if ma5_turn == "continue_up" and consec_top >= 5:
        return "main_rise"
    if ma5_turn == "turn_down":
        return "divergence" if blast_rate > 0.30 else "decay_1"
    if ma5_turn == "continue_down":
        return "decay_2"
    return "warming"  # 兜底
```

`sentiment_value` = 估算的"情绪锚定值"，简化为 `red_count`（旧 spec 同一思路）。

### 6.4 `cycle_switch_node`

输入：今日 + 昨日 state（从 SQLite checkpointer 读上一次 `post_mortem` 的快照；首次运行时无前日数据，赋 False）

判定：
- `is_new_cycle_day`：昨日 `emotion_phase ∈ {chaos, decay_2}` + 今日 `emotion_phase ∈ {recovery, warming}` + `consec_top` 提升
- `is_only_rebound`：连续 5 日下跌后单日反弹且次日不延续（需要回看 5 日历史，依赖 checkpointer 历史快照）
- `money_effect`：v1 简化为 `positive` if `limit_up_count > 50 else "neutral" if > 20 else "negative"`

> 边界处理：首次运行（无前日 checkpoint）所有 cycle_switch 标志赋 False，并写 `errors: ["cycle_switch: 无前日数据,标志位降级为 False"]`。

## 7. ANALYZE 阶段节点

### 7.1 `theme_analyst_node` (LLM)

调 DeepSeek 把当日涨停股聚成题材，判每个题材的演绎阶段、主线、theme_axis。详见 § 9 LLM 节点。

`--no-llm` 时 fallback：以 `stock_board_concept_cons_ths` 的概念归类直接当题材，所有题材 phase 标 `horizontal`，main_theme 取涨停股最多的概念。

### 7.2 `leader_tracker_node`

输入：`raw["ztb_today"]` + `themes`（来自 theme_analyst） + 个股日线（按需懒加载）

仅日线启发式（接受精度损失）：
- **strength score** = `连板数 * 2 + 封单亿 + (10 if 首封时间 < "10:00" else 0) - 炸板次数`
- **role** 分配（每个题材独立排序）：
  - 最高 score → `total`（总龙）
  - 次高 score 且属于同题材 → `companion`（伴生）
  - 连板数 < 龙头 - 2 但 score 高 → `complement`（补涨）
  - 流通盘 > 100 亿且连板 ≥ 2 → `capacity`（容量龙）
- **succession_status**：
  - 龙头连板 ≥ 4 且今日未炸板 → `healthy`
  - 龙头连板 ≥ 4 且今日炸板（首次分歧）→ `first_div`
  - 连续 2 日炸板 → `second_div`
  - 龙头跌破 5% → `broken`
  - 老龙断板 + 新龙出现（题材内换龙）→ `trans`
- `div_count`：从 SQLite checkpointer 读历史，今日是龙头第几次出现"高位低开 / 炸板"

### 7.3 `pattern_matcher_node`（真值表 + LLM 兜底）

详见 § 9。

## 8. DECIDE 阶段：4 个子图

每个子图都是 `StateGraph[*State]`，结构 = **filter → score → rank**，输出 `candidates` 列表（top_k = 5）。

### 8.1 `first_board` 子图（一进二）

```python
def build_fb_subgraph():
    g = StateGraph(FirstBoardState)
    g.add_node("filter",  fb_filter)
    g.add_node("score",   fb_score)
    g.add_node("rank",    fb_rank)
    g.add_edge(START, "filter")
    g.add_edge("filter", "score")
    g.add_edge("score", "rank")
    g.add_edge("rank", END)
    return g.compile()
```

**filter**：从 `raw["ztb_yesterday"]` 取昨日首板（连板数=1），剔除 ST/退/次新（上市 < 60 日）/一字板（开盘价 ≥ 涨停价×0.999）。

**score**：4 维加权
- 主线题材命中 → +0.4
- 封单 > 1 亿 → +0.2
- 首封时间 < "10:00" → +0.2
- 炸板次数 == 0 → +0.2

**rank**：top 5，建议仓位 = 0.10。

### 8.2 `weak_to_strong` 子图（弱转强 · 日线近似）

无分时数据，用日线特征近似：
- **昨日烂板** = 昨日涨停 ∧ 昨日炸板次数 ≥ 2 ∧ 收盘 < 涨停价 × 1.005
- **今日竞价爆量** = 今日开盘价 / 昨日收盘价 > 1.05
- **5min 秒板**（近似）= 今日首封时间 < "09:35"
- 排除一字开
- 主线题材 + 5min 秒板 + 早盘封单大 → 高分

### 8.3 `continuous` 子图（二进三 / 分歧三板）

筛 `连板数 ∈ {2, 3}`，命中 `pattern_hits` 中 "first_to_continuous"。打分：
- 连板高度匹配当前 `sentiment_value`（情绪低只玩 2B,情绪高才上 3B+）
- 题材共振（同题材至少 3 票连板）
- 同板块连板梯队完整度（领涨 + 跟风 ≥ 3 票）

### 8.4 `setback_reversal` 子图（首阴反包）

筛过去 5 日内有过涨停 + 今日是阴线 + 收盘 ≤ 昨日开盘 × 1.005。打分：
- 阴线跌幅深（反包空间大）
- 量能缩量（更易反包）
- 仍属主线题材
- 当前 `emotion_phase ∈ {divergence}` 时加权

### 8.5 子图统一约定

- 子图私有字段一律以 `_` 前缀（如 `_fb_pool` / `_fb_scored`），不出子图
- 每个子图最多 emit 5 个 candidate
- 子图失败不抛 → 写 `errors`，父图 `risk_guard` 看到 errors 时降级提示
- `Send` 传入的切片永远只读

## 9. LLM 节点

### 9.1 DeepSeek 客户端

```python
# llm/deepseek.py
import os
from langchain_openai import ChatOpenAI

def get_llm(temperature: float = 0.3) -> ChatOpenAI:
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
        temperature=temperature,
        timeout=30,
        max_retries=1,
    )
```

`.env` 文件：
```
DEEPSEEK_API_KEY=sk-84398b6b73704500911b627a97444f57
```

### 9.2 Pydantic schema

```python
# llm/schemas.py
from pydantic import BaseModel, Field
from typing import Literal

class ThemeOut(BaseModel):
    name: str
    members: list[str]
    leader: str | None
    phase: Literal["budding","horizontal","vertical","switching","exhausted"]
    catalysts: list[str]
    resonance_score: float = Field(ge=0, le=1)

class ThemeAnalystOut(BaseModel):
    themes: list[ThemeOut]
    main_theme: str | None
    theme_axis: Literal["horizontal","vertical","switching","exhausted"]

class PatternEdgeOut(BaseModel):
    emotion_phase: Literal[
        "chaos","recovery","warming","main_rise",
        "climax","divergence","decay_1","decay_mid","decay_2"
    ]
    confidence: float = Field(ge=0, le=1)
    reason: str
```

### 9.3 ThemeAnalyst prompt

见 § 5 节点描述。每日必调 1 次，token 预算 ≈ 3000 in / 1500 out。

### 9.4 PatternMatcher 真值表

```python
ROUTE_TABLE = {
    ("chaos",      False, "broken",     "*"): ["L1_first_board", "L2_weak_to_strong"],
    ("recovery",   True,  "first_div",  "up"): ["L1_first_board", "L2_weak_to_strong"],
    ("warming",    False, "healthy",    "up"): ["L4_strong_2b", "first_to_continuous"],
    ("main_rise",  False, "healthy",    "up"): ["leader_relay", "capacity_main"],
    ("climax",     False, "*",          "*"): [],
    ("divergence", False, "first_div",  "*"): ["S2_setback_reversal"],
    ("divergence", False, "second_div", "*"): [],
    ("decay_1",    False, "broken",     "*"): [],
    ("decay_2",    False, "broken",     "*"): ["sunflower_1_only_rebound"],
}

PATTERN_TO_SUBAGENT = {
    "L1_first_board":      "first_board",
    "L2_weak_to_strong":   "weak_to_strong",
    "L4_strong_2b":        "first_board",
    "first_to_continuous": "continuous",
    "S2_setback_reversal": "setback_reversal",
    # leader_relay / capacity_main / sunflower_* 等留 v2,本期跳过(子图未实现)
}
```

> **`_lookup_route` 通配语义**：先按 4 元组精确匹配；若未命中，把任一 key 替换为 `"*"` 再查，按 (succession, index, is_new_cycle) 顺序逐一放宽，直到命中为止。仍无命中 → 返回 `[]`（视为空仓）。

### 9.5 LLM 边缘检测

触发 LLM 重判 `emotion_phase` 的条件（任一）：
- 涨停家数贴近阈值（±10% 内：980-1020 / 3960-4040 / 90-110）
- MA5 拐点状态为 `flat`
- 炸板率 > 40%
- 连板梯队断层（最高 5+ 但 3-4 板少于 2 只）

LLM 返回的 `emotion_phase` 仅当 `confidence > 0.7` 且与规则结果不同时才覆盖；否则忽略。

LLM 失败 / token 超限 → 写 `errors`，沿用规则结果。

### 9.6 LLM 用量预算

每日单次跑全图：
- ThemeAnalyst：1 次必调
- PatternMatcher：约 30% 概率触发边缘检测
- 每次 ≈ ¥0.005 (DeepSeek 价格)
- 单日 < ¥0.01

## 10. 后置节点（Arbitrage / RiskGuard / TradePlanner / PostMortem）

### 10.1 `arbitrage_node`（4 类硬编码套利）

```python
def arbitrage_node(state) -> dict:
    arbs = []
    arbs += _ladder_arb(state)        # 梯队套利
    arbs += _complement_arb(state)    # 补涨套利
    arbs += _new_cycle_arb(state)     # 新周期套利
    arbs += _drop_out_arb(state)      # 竞争掉队套利
    return {"arb_opportunities": arbs}
```

每类 < 30 行，纯日线 + leader_stack + themes 数据。

### 10.2 `risk_guard_node`（27 条禁忌 + 仓位上限）

```python
@dataclass
class Taboo:
    name: str
    desc: str
    predicate: Callable[[MarketState, Candidate], bool]
    drop: bool                        # True=直接剔除, False=只标 flag

TABOOS = [
    Taboo("no_chase_climax", "高潮日不接力首封",
          lambda s, c: s["emotion_phase"] == "climax", drop=True),
    Taboo("no_w2s_in_decay", "退潮初期不做弱转强",
          lambda s, c: s["emotion_phase"] == "decay_1" and c["pattern_id"] == "L2_weak_to_strong",
          drop=True),
    Taboo("max_consec_in_chaos", "情绪冰点最高连板 ≥ 3 不接力",
          lambda s, c: s["emotion_phase"] == "chaos" and _consec(c) >= 3,
          drop=True),
    # ... v1 实现 ≥ 10 条核心禁忌,留好接口后续补到 27 条
]

def risk_guard_node(state) -> dict:
    surviving, flags = [], []
    for c in state.get("candidates", []):
        kept = True
        for t in TABOOS:
            if t.predicate(state, c):
                flags.append(f"{c['code']} 触发禁忌「{t.desc}」")
                if t.drop: kept = False; break
        if kept: surviving.append(c)
    pos_max = _zone_total_max(state["emotion_phase"], state["index_phase"])
    return {
        "final_candidates": surviving,         # 写到新字段(非 reducer)
        "risk_flags": flags,
        "_position_total_max": pos_max,
    }
```

仓位区间映射沿用 `market_sentiment` spec 思路：
- `recovery` / `warming` / `main_rise` → 进攻区（单 0.5 / 总 1.0）
- `climax` / `decay_1` / `divergence` → 防守区（单 0.2 / 总 0.3）
- `chaos` / `decay_2` → 震荡区（单 0.2 / 总 0.2，但允许打首板）

v1 必须实现的核心禁忌（≥ 10 条）：
1. 高潮日不接力首封
2. 退潮初期不做弱转强
3. 冰点高连板（≥3）不接
4. 老龙断板当日不上车
5. 一字开板不打
6. 上市 < 60 日（次新）不进首板池
7. ST / *ST / 退市股不进任何池
8. 当日已涨停的不进次日候选（套利场景除外）
9. 总仓位超过 zone 上限时按 score 降序裁剪
10. 单票仓位超过 suggested_position 时截断

### 10.3 `trade_planner_node`

```python
def trade_planner_node(state) -> dict:
    finals = state.get("final_candidates", [])[:8]
    pos_total = state.get("_position_total_max", 0.5)
    plan = build_plan(finals, pos_total, state["target_date"])
    return {"plan": plan}
```

按 score 排序按比例分配仓位，单票 ≤ `suggested_position`。

### 10.4 `post_mortem_node`

写入 `runs/{date}/`：
- `report.json`：完整 state 序列化（剔除 `raw` 中的 DataFrame）
- `report.md`：人类可读报告（详见 § 12）
- `state_snapshot.json`：用于次日 `cycle_switch` 节点比对

## 11. 数据层（`data/akshare_client.py`）

### 11.1 接口清单

| 数据 | akshare 函数 | 频次 | 缓存 key |
|---|---|---|---|
| 当日涨停池 | `stock_zt_pool_em(date)` | 1/天 | `ztb_{date}` |
| 昨日涨停池 | `stock_zt_pool_em(prev_date)` | 1/天 | `ztb_{prev_date}` |
| 昨日炸板池 | `stock_zt_pool_zbgc_em(prev_date)` | 1/天 | `zb_{prev_date}` |
| 上证 / 创业板日线 | `stock_zh_index_daily_em(symbol)` | 1/天 | `idx_{symbol}_daily` |
| 涨跌家数 | `stock_market_activity_legu()` (+ fallback) | 1/天 | `activity_{date}` |
| 个股日线 | `stock_zh_a_hist(symbol, "daily", ...)` | N/天 | `kline_{code}_{end}` |
| 同花顺概念成分 | `stock_board_concept_cons_ths(symbol)` | M/天 | `concept_{name}` |
| 同花顺概念列表 | `stock_board_concept_name_ths()` | 1/天 | `concept_list_{date}` |
| 上市信息 | `stock_info_a_code_name()` | 1/天 | `code_listdate` |

### 11.2 客户端封装

```python
import akshare as ak
import pandas as pd
from .cache import disk_cache

class AkshareClient:
    def __init__(self, cache_dir: str = "data_cache"):
        self.cache_dir = cache_dir

    @disk_cache(ttl="eod")
    def limit_up_pool(self, date: str) -> pd.DataFrame:
        return _retry(lambda: ak.stock_zt_pool_em(date=date.replace("-","")))

    @disk_cache(ttl="eod")
    def market_activity(self, date: str) -> pd.DataFrame | None:
        try:
            return ak.stock_market_activity_legu()
        except Exception:
            spot = ak.stock_zh_a_spot_em()
            return pd.DataFrame([{
                "date": date,
                "red_count":   int((spot["涨跌幅"] > 0).sum()),
                "green_count": int((spot["涨跌幅"] < 0).sum()),
                "limit_up":    int((spot["涨跌幅"] >= 9.9).sum()),
            }])

    # ...其他接口同模式
```

### 11.3 缓存策略

- 落 `data_cache/{date}/{key}.parquet`
- TTL = `"eod"`：同一交易日内永久有效，跨日失效
- 写入 `pd.to_parquet`、读取 `pd.read_parquet`（依赖 `pyarrow`）
- 重跑当日图 0 网络成本

### 11.4 重试

```python
def _retry(fn, attempts: int = 3, backoff: float = 1.5):
    last = None
    for i in range(attempts):
        try: return fn()
        except Exception as e:
            last = e
            time.sleep(backoff ** i)
    raise last
```

3 次失败后抛异常，由调用节点捕获并写 `errors`。

## 12. CLI + 输出

### 12.1 CLI

```bash
python -m youzi_agent                          # 跑最近交易日
python -m youzi_agent 2026-04-25               # 指定日期
python -m youzi_agent 2026-04-25 --no-llm      # 关 LLM,完全离线
python -m youzi_agent 2026-04-25 --refresh     # 忽略缓存重拉
python -m youzi_agent 2026-04-25 --json        # 仅输出 JSON 到 stdout
```

退出码：
- 0 = 成功
- 1 = 数据失败（market_sensor 抛异常，无 plan）
- 2 = 部分节点 errors（plan 生成但带警告）

### 12.2 报告模板（`runs/{date}/report.md`）

```markdown
# 游资策略复盘 · 2026-04-25

## 情绪诊断
- emotion_phase: **recovery**
- 涨停 87 | 最高连板 4 | 炸板率 18.3%
- 五日线: bottom_grinding | 新周期确立: ✅

## 主线
**核电** (vertical, score 0.82)
- 龙头: 中核科技 600202 (3B)
- 跟风: 江苏神通, 中国核建, 浙富控股, ...

## 候选池 (4)
| code | name | pattern | score | reason | 仓位 |
|---|---|---|---|---|---|
| 600202 | 中核科技 | L1_first_board | 0.8 | 主线·封单2.3亿·09:43封板 | 0.10 |

## 风控告警
- ⚠️ 600xxx 触发禁忌「退潮初期不做弱转强」(已剔除)

## 套利机会
- 补涨套利: 浙富控股 (低位 2B,核电同属性)

## 建议总仓位上限
- 单票 ≤ 50% / 总仓 ≤ 100% (进攻区·主升共振)

## 节点错误
- (无)
```

## 13. 测试策略

```
tests/
├── conftest.py                    # 注入 MockAkshareClient
├── fixtures/
│   ├── 2026-04-23/                # 真实日子的 parquet 快照
│   └── synthetic_chaos.parquet    # 人工构造的冰点日
├── test_nodes/
│   ├── test_emotion.py
│   ├── test_pattern_matcher.py    # 真值表 9 分支全覆盖
│   ├── test_theme_analyst.py      # mock LLM
│   └── ...
├── test_subagents/
│   ├── test_first_board.py
│   └── ...
├── test_data/
│   └── test_akshare_client.py     # mock requests + fallback
└── test_e2e.py                    # 全图跑 fixtures/ → 验 plan
```

约束：
- 所有 LLM 节点必须有 `--no-llm` 路径，单测默认走 `--no-llm`
- E2E 测试不打网络、不调 LLM
- pytest 标记 `@pytest.mark.live` 区分需要真实网络的烟测，CI 不跑

## 14. 依赖（`pyproject.toml`）

```toml
[project]
name = "youzi-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "langgraph>=0.2.50",
    "langgraph-checkpoint-sqlite>=2.0",
    "langchain-openai>=0.2",
    "akshare>=1.13",
    "pandas>=2.0",
    "pyarrow>=15",
    "pydantic>=2.5",
    "rich>=13",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-cov", "ruff", "mypy"]

[project.scripts]
youzi-agent = "youzi_agent.cli:main"
```

## 15. 已知风险与未决事项

1. **akshare 接口可用性**：`stock_market_activity_legu` 和 `stock_zt_pool_em` 是 v1 关键依赖，实施第一步必须验证；任何接口字段名变化都会导致解析挂掉，已 pin `akshare>=1.13`。
2. **首日运行无前日 checkpoint**：`cycle_switch` 节点降级所有跨日标志为 False 并写 errors，不阻断流程。
3. **过程信息缺失**：日线近似的弱转强 / 反包模式精度有损，子图打分阈值需要在真实数据跑 ≥ 10 个交易日后回校。
4. **LLM 兜底误判**：`pattern_matcher` 的 LLM 边缘判断可能频繁改判，需要监控触发率，必要时收紧 `confidence` 阈值（v1 = 0.7）或缩小边缘窗口。
5. **27 条禁忌 v1 只实现 10 条**：剩余在 v2 补全；测试覆盖应保证后续新增禁忌不会改变已有 candidate 的过滤行为。
6. **DeepSeek 速率 / 服务波动**：单日调用 ≤ 2 次，风险极小；但需验证 `with_structured_output` 在 DeepSeek 上的兼容性（必要时降级为 JSON 模式 + 手动解析）。
7. **本系统仅供研究 / 实盘辅助，不替任何人下单**；plan 必须经人工二次审查后才能转化为订单。
