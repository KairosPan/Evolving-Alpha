# A股市场情绪状态分析器 — 设计文档

**日期**: 2026-04-24
**规格来源**: `market.md`（基于880005涨跌家数指数的细颗粒度量化交易关键词体系）

## 1. 目标与范围

构建一个**纯规则驱动**的 A 股市场情绪状态分析器。给定一个交易日，输出当日的：

- 核心指标（RedCount、MA5、MA3、方向）
- 情绪周期标签（CycleTag，8 选 1）
- MA3/MA5 组合状态（4 选 1）
- 启用/禁用的交易模式清单
- 仓位上限建议
- 风控告警

**非目标 (v1 不做)**：
- 同花顺 CCI(5)、昨日炸板股指数（akshare 不直接提供）
- 凯利公式自动计算（缺历史回测的 W/R，提供独立工具函数但不进入主流水线）
- 账户回撤熔断（无账户状态）
- 个股选股、盘口分析、集合竞价信号
- 实时交易、订单执行
- LangGraph 编排（用户明确要求纯规则）

## 2. 架构

**Approach B — 流水线模块**。将分析过程拆为顺序执行的纯函数，每一步消费上一步的输出。结构等价于一个 LangGraph，但用 Python 顺序调用替代图调度，后期需要加 LLM 节点或图分支时改造成本极低。

```
fetch_data → indicators → cycle_classify → mode_recommend → position_advise → risk_check → assemble_report
```

每一步签名统一为 `def step(state: dict) -> dict`，输入输出都是结构化字典，纯函数无副作用。

## 3. 模块结构

```
market_sentiment/
├── __init__.py          # 暴露 analyze() 主入口
├── data.py              # akshare 拉取 880005 涨跌家数
├── indicators.py        # MA5、MA3 计算与方向判定
├── cycle.py             # CycleTag 分类 + MA3/MA5 组合状态
├── modes.py             # 交易模式启用/禁用清单
├── position.py          # 仓位上限建议
├── risk.py              # 风控告警生成
├── analyzer.py          # 流水线编排
├── kelly.py             # 凯利公式工具（独立，不进流水线）
└── __main__.py          # CLI 入口
```

每个文件 < 200 行。模块边界清晰：`data` 负责 IO，其余全部纯计算。

## 4. 数据层 (`data.py`)

**akshare 接口**：使用 `ak.stock_zh_a_spot()` 不行（实时快照），需要历史数据。880005 是通达信指数，akshare 中对应：

```python
import akshare as ak
df = ak.stock_zh_index_daily_em(symbol="sh000001")  # 备选：用上证综指反推
# 实际目标：找到能返回每日全市场红盘家数的接口
```

**实现策略**：
- 主路径：尝试 `ak.stock_market_activity_legu()`（同花顺市场活跃度）或类似接口获取每日涨/跌家数
- 备选路径：`ak.stock_zh_a_hist()` 拉全 A 股每日数据，本地聚合 RedCount = 收盘价 > 开盘价的股票数（成本高，仅作 fallback）
- v1 优先用 akshare 现成的市场情绪接口；若不可用，提供 mock 数据加载器供测试

**输出**：
```python
{
    "dates": ["2026-04-01", ..., "2026-04-23"],   # 至少 30 个交易日
    "red_counts": [1234, 1567, ...]                # 对齐 dates
}
```

**缓存**：本地 SQLite 或 CSV 缓存，避免重复拉取。v1 简化为内存 dict + 文件 pickle。

## 5. 指标层 (`indicators.py`)

```python
def compute_ma(values: list[float], window: int) -> list[float | None]:
    """前 window-1 项为 None，之后为简单移动平均"""

def ma_direction(ma_series: list[float], lookback: int = 1) -> Literal["up", "down", "flat"]:
    """对比当日 MA 与 lookback 日前的 MA，差值绝对值 < 5 视为 flat"""

def ma5_turn_today(red_counts: list[float]) -> Literal["turn_up", "turn_down", "continue_up", "continue_down", "flat"]:
    """
    判定今日 MA5 拐点：
    - 今日 MA5 > 昨日 MA5 且 昨日 MA5 < 前日 MA5 → turn_up
    - 今日 MA5 < 昨日 MA5 且 昨日 MA5 > 前日 MA5 → turn_down
    - 连续 2 日上升 → continue_up
    - 连续 2 日下降 → continue_down
    - 其他 → flat
    """
```

**flat 阈值**: |Δ| < 5（家）。可调常量。

## 6. 周期分类层 (`cycle.py`)

### 阈值常量（当前标准，2026 年视角）

```python
ICE_THRESHOLD = 1000           # RedCount ≤ 1000 → IcePoint
CLIMAX_THRESHOLD = 4000        # RedCount ≥ 4000 → Climax
MA5_LOWER_RAIL = 2000          # MA5 < 2000 → 下轨
MA5_UPPER_RAIL = 2500          # MA5 > 2500 → 上轨
LOW_SHAKE_RANGE = (1800, 2000) # MA5 在此区间窄幅 → LowShake
HIGH_SHAKE_RANGE = (2500, 2800)# MA5 在此区间窄幅 → HighShake
SHAKE_VOLATILITY = 100         # 近 5 日 MA5 极差 < 此值 → 视为窄幅
```

### CycleTag 判定优先级

逐条判定，命中即返回（短路求值）：

1. `red_count ≤ ICE_THRESHOLD` → **IcePoint**
2. `red_count ≥ CLIMAX_THRESHOLD` → **Climax**
3. `ma5_turn == "turn_up"` → **TurnUp**
4. `ma5_turn == "turn_down"` → **TurnDown**
5. `ma5_turn == "continue_up"` → **MainRally**
6. `ma5_turn == "continue_down"` → **Downtrend**
7. `MA5 ∈ HIGH_SHAKE_RANGE` 且近 5 日 MA5 极差 ≤ `SHAKE_VOLATILITY` → **HighShake**
8. `MA5 ∈ LOW_SHAKE_RANGE` 且近 5 日 MA5 极差 ≤ `SHAKE_VOLATILITY` → **LowShake**
9. 兜底 → **Neutral**（标记"模糊地带"）

### MA3/MA5 组合状态

依据 market.md 表格：

| MA3 | MA5 | combo_state |
| --- | --- | --- |
| up | up | 主升共振 |
| up | down | 下跌中继/反弹 |
| down | up | 上升中继/分歧 |
| down | down | 双杀退潮 |

flat 视为同向（保守处理：若 MA5 flat，按上一交易日方向延续）。

## 7. 模式推荐层 (`modes.py`)

依据 market.md 第三章表格，建立映射：

```python
MODE_ENABLE_MATRIX = {
    "IcePoint":   ["ExtremeArbitrage", "SecondWaveWrap"],
    "TurnUp":     ["FirstLimit", "SecondWaveWrap", "1To2", "DipBuy"],
    "MainRally":  ["FirstLimit", "DipBuy", "1To2"],
    "Climax":     ["ExtremeArbitrage", "AccumulationIntraday"],
    "TurnDown":   ["AccumulationIntraday"],
    "Downtrend":  [],
    "LowShake":   ["FirstLimit", "SecondWaveWrap"],
    "HighShake":  ["AccumulationIntraday"],
    "Neutral":    [],
}

MODE_DISABLE_MATRIX = {
    "IcePoint":   [],
    "TurnUp":     [],
    "MainRally":  ["AccumulationIntraday"],
    "Climax":     ["FirstLimit", "1To2", "DipBuy", "SecondWaveWrap"],
    "TurnDown":   ["FirstLimit", "1To2", "DipBuy"],
    "Downtrend":  ["FirstLimit", "1To2", "DipBuy", "SecondWaveWrap", "AccumulationIntraday"],
    "HighShake":  ["FirstLimit", "1To2", "SecondWaveWrap"],
    "LowShake":   ["ExtremeArbitrage"],
    "Neutral":    ["ExtremeArbitrage"],
}
```

输出：
```python
{
    "enabled": ["FirstLimit", "1To2", ...],
    "disabled": ["AccumulationIntraday"],
    "rationale": "TurnUp 周期，启用进攻类模式..."
}
```

## 8. 仓位建议层 (`position.py`)

依据 market.md 第四章决策树：

```python
ZONES = {
    "进攻区": {"single_max": 0.5, "total_max": 1.0, "tone": "积极进攻"},
    "防守区": {"single_max": 0.2, "total_max": 0.3, "tone": "降仓控风险"},
    "震荡区": {"single_max": 0.2, "total_max": 0.2, "tone": "严格控仓"},
}

CYCLE_TO_ZONE = {
    "IcePoint": "进攻区",
    "TurnUp": "进攻区",
    "MainRally": "进攻区",
    "Climax": "防守区",
    "TurnDown": "防守区",
    "Downtrend": "防守区",
    "HighShake": "防守区",
    "LowShake": "震荡区",
    "Neutral": "震荡区",
}
```

输出 `{single_max, total_max, zone, tone, note}`。

## 9. 风控告警层 (`risk.py`)

基于"周期切换"和"阈值穿越"生成告警。需要前一日的 cycle_tag 作为对比。

| 触发条件 | 告警等级 | 文案 |
| --- | --- | --- |
| 今日首次进入 Climax | 高 | 已进入高潮区，禁开新仓，去弱留强 |
| 今日 cycle 从上升类 → TurnDown | 高 | MA5 拐头向下确认，系统级减仓信号 |
| 双杀退潮（MA3↓ MA5↓） | 高 | 强制降仓或空仓，等待冰点 |
| 今日首次进入 IcePoint | 中 | 情绪冰点确认，次日反弹计划准备 |
| TurnUp 与 MA3 同步上拐 | 中 | 主升共振信号，胜率最高的进攻节点 |
| MA5 接近上轨（>2300） | 低 | 接近高潮区，逐步降低单票仓位 |

## 10. 流水线编排 (`analyzer.py`)

```python
def analyze(target_date: str | None = None, lookback_days: int = 30) -> dict:
    """主入口。target_date 默认最近交易日。"""
    state = {"target_date": target_date, "lookback_days": lookback_days}
    state = fetch_data(state)
    state = compute_indicators(state)
    state = classify_cycle(state)
    state = recommend_modes(state)
    state = advise_position(state)
    state = check_risks(state)
    return assemble_report(state)
```

## 11. CLI (`__main__.py`)

```bash
python -m market_sentiment              # 分析最近交易日
python -m market_sentiment 2026-04-23   # 分析指定日期
python -m market_sentiment --json       # 输出 JSON
```

默认输出格式化的中文报告。

## 12. 输出 schema

```python
{
  "date": "2026-04-23",
  "indicators": {
    "red_count": 1234,
    "ma5": 1850.2,
    "ma3": 1900.1,
    "ma5_dir": "up",     # up | down | flat
    "ma3_dir": "up",
    "ma5_turn": "turn_up" # turn_up | turn_down | continue_up | continue_down | flat
  },
  "cycle_tag": "TurnUp",
  "combo_state": "主升共振",
  "modes": {
    "enabled": ["FirstLimit", "SecondWaveWrap", "1To2", "DipBuy"],
    "disabled": [],
    "rationale": "..."
  },
  "position": {
    "zone": "进攻区",
    "single_max": 0.5,
    "total_max": 1.0,
    "tone": "积极进攻",
    "note": "MA5 拐头向上，单票可半仓+，总仓积极"
  },
  "risk_alerts": [
    {"level": "中", "message": "MA5 与 MA3 同步上拐，主升共振信号"}
  ],
  "summary": "TurnUp + 主升共振，进攻区，建议聚焦主线龙头"
}
```

## 13. 测试策略

- **单元测试**：每个纯函数（indicators、cycle、modes、position、risk）用人工构造的 RedCount 序列覆盖各 CycleTag 分支
- **集成测试**：mock akshare 返回，验证 `analyze()` 端到端
- **冒烟测试**：用 akshare 拉一个真实最近交易日，确认整条链路跑通

## 14. 依赖

```
akshare >= 1.12.0
pandas >= 2.0
```

无需 langgraph、langchain、openai 等。

## 15. 风险与未决事项

1. **akshare 接口可用性**：880005 全市场涨跌家数的最佳数据源未验证。实施时第一步就要确认数据接口，若无现成接口需要 fallback 到 hist 聚合方案。
2. **阈值动态化**：market.md 强调"阈值需随上市公司总数调整"。v1 写死当前标准（5000+ 公司），后期可加 `thresholds.py` 配置文件。
3. **拐点定义的灵敏度**：用 1 日方向变化定义拐点容易误报（震荡日频繁拐头）。可能需要加 2 日确认或方向变化幅度阈值。v1 用最朴素定义，后续按实测调整。
