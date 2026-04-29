# youzi-agent Web App — 设计文档

**日期**: 2026-04-28
**规格来源**: 把现有 CLI（`youzi-agent`）的多智能体研究 pipeline 包装成本地浏览器盯盘台
**关联**:
- `docs/superpowers/specs/2026-04-26-youzi-agent-design.md`（被包装的 graph）
- `A股游资智能体_LangGraph设计.md`（方法论源头，"盘前盘后人工 review"在本设计中落地）

---

## 1. 目标与范围

把 `src/youzi_agent/` 的 LangGraph 多智能体 pipeline 暴露成一个**单人本地浏览器应用**，提供流式节点进度可视化、关键决策点的人工 review、以及历史复盘。

### v1 必交付
- 单人本地（localhost-only），无认证
- 手动触发（用户点 "Run"），无定时/分钟级 polling/桌面通知
- 单仓 monorepo：`apps/api`（FastAPI）+ `apps/web`（Next.js）+ 现 `src/youzi_agent/` 不动
- LangGraph 流式 SSE 推节点进度 + state 增量
- 3 个关键节点的人工 interrupt：`PatternMatcher` / `RiskGuard` / `TradePlanner`
- Dashboard 三栏 console：左上下文 sticky / 中央可切视图 / 右节点流 + interrupt 抽屉
- 中央 7 个视图：概览（默认）/ 题材 / 龙头 / 候选池 / 套利 / 风控 / 计划
- 候选池行内 sparkline + 龙头抽屉 60 日 K 线（lightweight-charts）
- 历史日 picker：直接读 `runs/YYYY-MM-DD/state_snapshot.json`，单日加载（不做对比）
- Dashboard 单元格内联编辑 → 重跑下游（v1 仅开放 4 类字段：`pattern_hits` / `leader_stack` / `themes.*.phase` / `risk_flags`）
- CLI 保留并复用同一 `GraphRuntime`（interrupt 自动批准）

### v1 非目标
- 多用户 / 认证 / 公网部署
- 自动定时跑 / 桌面/邮件/IM 提醒
- 真实分钟级数据 ingest / 集合竞价 ExpectationDiff 节点
- 历史双日并排对比视图 / 跨日相似性
- 重图表台（板块热力图、涨停瀑布、资金流、龙头接力树状图）
- 题材抽屉 K 线 / 自定义指标 / 笔记标注
- 视觉回归 / 性能基准 / 安全审计

### 关键决策回顾

| # | 问题 | 决定 |
|---|---|---|
| 1 | 定位 | C — 全功能盯盘台（流式 + interrupt + dashboard 编辑） |
| 2 | 部署 | A — 单人本地 |
| 3 | 技术栈 | A — Next.js + FastAPI 单仓 |
| 4 | 触发节奏 | C — 手动触发，无提醒 |
| 5 | HITL 粒度 | B — 仅 `PatternMatcher`/`RiskGuard`/`TradePlanner` 3 节点 interrupt |
| 6 | 主布局 | C — 三栏 Console |
| 7 | 图表深度 | B — 关键位置嵌 K 线（lightweight-charts） |
| 8 | 历史 | B — 日 picker，单日加载 |
| 调整 | 工具链 | pip（非 uv），npm（非 pnpm），`src/youzi_agent/` 不重命名 |

---

## 2. 架构总览

```
┌──── Browser (localhost:3000 dev / :8000 prod) ──────────────────────────┐
│  左：上下文 sticky │  中：当前视图（6 选 1）│  右：Run 流 + interrupt   │
└─────────┬──────────────────┬─────────────────────────────┬──────────────┘
          │ /api/runs/{date} │ /api/state/{tid}/edit       │ /api/run/{tid}/stream (SSE)
          │ /api/runs        │   POST {path, value}         │ /api/run/{tid}/resume (POST)
          │                                                  │
┌─────────▼──────────────────────────────────────────────────▼────────────┐
│  FastAPI (apps/api)                                                      │
│  ├─ HTTP/SSE 路由（fastapi + sse-starlette）                             │
│  ├─ GraphRuntime: asyncio queue + interrupt future + dirty-node 重跑     │
│  └─ import youzi_agent.graph (= src/youzi_agent/)                        │
│  生产期还把 apps/web/out/ 当静态目录挂在 /                                │
└───────────┬───────────────────────────────────────┬─────────────────────┘
            ▼                                       ▼
   checkpoints.db (SqliteSaver)            runs/YYYY-MM-DD/{report.md,
   ← 唯一权威 state                         report.json, state_snapshot.json}
                                            ← 历史 picker 数据源
```

**关键 invariants**
- 唯一权威 state：LangGraph `SqliteSaver` 里 `thread_id`-keyed checkpoint
- 前端无本地真相（除 SSE 暂存的 in-flight run 状态）
- 历史日 picker 直接读 `runs/*/state_snapshot.json`，不重放 graph
- 每个 run 一个独立 SSE 连接；run 结束 SSE 关闭；不维护常驻 WebSocket
- thread_id = `{date}-{uuid8}`（沿用现 CLI 命名）；存 URL 查询参数

---

## 3. 后端 API 契约

### REST

| 方法 | 路径 | 用途 | 请求 | 响应 |
|---|---|---|---|---|
| `POST` | `/api/run` | 启动 run | `{date, use_llm?, refresh?}` | `{thread_id}` |
| `GET` | `/api/run/{tid}/stream` | SSE 节点流 + interrupt | — | `text/event-stream` |
| `POST` | `/api/run/{tid}/resume` | interrupt 续跑 | `{node, action: "approve"\|"edit", patch?}` | `{ok: true}` |
| `POST` | `/api/run/{tid}/abort` | 取消 | — | `{ok: true}` |
| `POST` | `/api/state/{tid}/edit` | 单元格编辑 → 重跑下游 | `{path, value}` | `{ok: true, rerun_tid}` |
| `GET` | `/api/state/{tid}` | 当前 checkpoint state | — | `MarketState` |
| `GET` | `/api/runs` | 历史列表 | `?limit=60` | `[{date, has_plan, candidates_count, errors_count}]` |
| `GET` | `/api/runs/{date}` | 历史单日 snapshot | — | `state_snapshot.json` 内容 |
| `GET` | `/api/kline/{code}` | K 线 | `?period=daily&days=60` | `[{time, open, high, low, close, volume}] + {limit_up_days}` |

### SSE 事件

```typescript
type RunEvent =
  | { type: "node_start";  node: string; ts: number }
  | { type: "node_end";    node: string; ts: number; state_patch: Partial<MarketState> }
  | { type: "node_error";  node: string; ts: number; message: string }
  | { type: "interrupt";   node: "PatternMatcher" | "RiskGuard" | "TradePlanner";
                           snapshot: MarketState; ts: number }
  | { type: "done";        final_state: MarketState; ts: number }
  | { type: "aborted";     reason: string; ts: number };
```

每条按 SSE `event:` + `data:` 编码。前端 `EventSource` 按 type 分发到 reducer。`state_patch` 为节点级增量。

### Interrupt review payload

| 节点 | 主要内容 | 可编辑 |
|---|---|---|
| `PatternMatcher` | `pattern_hits` 列表 + 路由分发预览 + 命中理由 | 增删 hit、改 `target_subagent` |
| `RiskGuard` | 触发 `risk_flags` + 受影响候选 + 仓位建议 | 接受/驳回每条 flag、覆盖仓位上限 |
| `TradePlanner` | 候选最终列表 + 仓位分配 + 三段执行计划 | 改候选权重、改三段 notes |

### 字段编辑白名单（v1）

只允许 `pattern_hits` / `leader_stack` / `themes.*.phase` / `risk_flags`。其他字段后端拒绝（返回 400）。

### 重跑下游协议

```
POST /api/state/{tid}/edit {path, value}
  → 后端校验 path
  → jsonpatch 改 snapshot
  → 查 path → 起点节点映射，找出 first dirty node
  → graph.update_state(cfg, new_state, as_node=first_dirty)
  → 起新的 SSE 通道（新 tid，便于审计）
  → 返回 {rerun_tid}
```

---

## 4. GraphRuntime 设计

`apps/api/graph_runtime.py` 把 LangGraph 的 stream/interrupt 包装成 asyncio 友好的 API。

```python
class GraphRuntime:
    def __init__(self, checkpoint_path: str = "checkpoints.db"):
        self._graph = build_graph(checkpoint_path=checkpoint_path)
        self._active: dict[str, asyncio.Queue[RunEvent]] = {}
        self._resume_signals: dict[str, asyncio.Future] = {}

    async def start(self, date, use_llm, refresh) -> str: ...
    async def stream(self, tid) -> AsyncIterator[RunEvent]: ...
    async def resume(self, tid, payload): ...
    async def edit(self, tid, path, value) -> str: ...
    async def abort(self, tid): ...
```

**核心机制**
1. 每个 `thread_id` 一个 `asyncio.Queue[RunEvent]` + 一个 `resume_signals[tid]: asyncio.Future`
2. `astream(stream_mode=["updates","values"])`：updates 给节点级增量，values 给 interrupt 时刻的完整 snapshot
3. interrupt 时阻塞在 `await fut`；resume() 调用 `fut.set_result(payload)`，然后 `update_state` + `astream(None, config=cfg)` 续跑（LangGraph 0.2 标准模式）
4. runtime 是 FastAPI 单例（`app.state.runtime`），本地单人无并发
5. 节点异常 → 捕获、推 `node_error` 事件、graph 整体 try/except 兜底推 `aborted`
6. SSE 队列保留最近 100 条事件，断线重连用 `Last-Event-ID` 续传

### graph 侧改动

`src/youzi_agent/` 几乎不动；`graph.py` 在 `pattern_matcher` / `risk_guard` / `trade_planner` 内部加 `interrupt(...)` 调用。CLI 走 "auto-approve" 模式（环境变量 `YOUZI_AUTO_RESUME=1` → runtime 收到 interrupt 立即 fut.set_result({})）。

---

## 5. 前端结构

### 目录

```
apps/web/
├── package.json                # npm，无 workspaces
├── next.config.mjs             # output: 'export'
├── tailwind.config.ts
├── app/
│   ├── layout.tsx
│   ├── page.tsx                # → /console?date=今天
│   ├── console/page.tsx
│   └── history/page.tsx
├── components/
│   ├── shell/                  # ThreeColumnLayout, TopBar
│   ├── left-context/           # EmotionGauge, PlanSummary, DateNavigator
│   ├── center-views/           # Overview/Themes/Leaders/Candidates/Arbitrage/Risk/Plan
│   ├── right-runstream/        # NodeTimeline, InterruptDrawer, reviews/{PatternMatcher,RiskGuard,TradePlanner}
│   ├── charts/                 # KLineChart, Sparkline (lightweight-charts wrapper)
│   └── ui/                     # shadcn/ui
└── lib/
    ├── api/                    # openapi-typescript 生成
    ├── sse.ts
    ├── store/                  # Zustand: runStore, stateStore, viewStore
    └── editing/                # <EditableCell path={...}>
```

### 状态管理三层

| 层 | 库 | 内容 |
|---|---|---|
| 服务端真相投影 | TanStack Query | `runs/`、`runs/{date}`、`kline/*` |
| 进行中 run 的 live | Zustand `runStore`/`stateStore` | SSE 推过来的节点进度 + state 增量；run 结束写入 React Query cache |
| UI 局部 | Zustand `viewStore` + useState | 中央视图切换、抽屉开关、选中行 |

### 路由

仅 `/console` 和 `/history`。中央视图切换走 `viewStore`，不改 URL（避免 SSE 重连）。

### 类型同步

`npm run gen:api` = `openapi-typescript http://localhost:8000/openapi.json -o lib/api/types.gen.ts`。pre-commit 跑一次。所有 `MarketState` / 子结构在两端共享。

### 视觉

- 暗色主题（v1 不做 light/dark 切换），等宽数字（`font-feature-settings: "tnum"`）
- KPI 用 emerald/red/amber 区分多/空/警告
- TanStack Table 候选池：sortable + virtualized

---

## 6. 图表集成

### 库选型
**lightweight-charts**（TradingView，~50KB gzip，金融原生）。

### 出现位置

| 场景 | 图表 | 数据 |
|---|---|---|
| 候选池表行内 | 30 日收盘 sparkline | `/api/kline/{code}?period=daily&days=30` |
| 龙头抽屉 | 60 日 K 线 + 涨停日红三角 + 5/10/20 日均线 | `/api/kline/{code}?period=daily&days=60` |
| 左栏情绪 sparkline | sentiment_value 7 日折线 | 聚合自 `runs/*/report.json` |

### 数据流

```
浏览器 → GET /api/kline/{code}
  → FastAPI 查 data_cache/kline/{code}_daily.parquet
  → 命中且当日已结 → 返回
  → 否则调 youzi_agent.data.akshare_client.get_kline → 写 cache
  → TanStack Query 缓存（staleTime 24h）
```

### 涨停日标注

`/api/kline` 响应附带 `limit_up_days: ["YYYY-MM-DD", ...]`。前端在 K 线上画红色三角 markers。

---

## 7. 错误处理 + 退化策略

**总原则**：graph 永远跑完；节点级失败写入 `errors[]` 不阻断；UI 用 banner/badge 暴露。

### 失败矩阵

| 失败源 | 当前行为 | Web 模式新增 |
|---|---|---|
| akshare 网络错误 | `market_sensor` 已有 retry + safe defaults | SSE 推 `node_error`；右栏节点变 amber |
| akshare 限频 | — | 全局 `asyncio.Semaphore`（≤2 并发）+ 退避 |
| DeepSeek 超时/限流 | 落规则 fallback | SSE 标 "fallback used" |
| DeepSeek schema 校验失败 | try/except 落 fallback | 同上 |
| graph 节点未捕获异常 | `graph.invoke` 整体崩 | runtime `_drive` try/except → 推 `aborted`；checkpoint 保留 |
| interrupt 超时（30 min） | — | runtime auto-approve（不改 snapshot），推 `node_end {auto_resumed: true}` |
| SSE 断开 | — | 后端 queue 保留最近 100 条；前端 `EventSource` 自动重连 + `Last-Event-ID` |
| edit 与 run race | — | edit 前 check `runtime.is_running(tid)`；前端 disable 编辑面板 |
| `runs/{date}/` 损坏 | CLI 抛错 | `/api/runs` 跳过 + 响应附 `warnings[]` |
| `checkpoints.db` 不可用 | CLI 启动失败 | FastAPI 启动 health check → 503 + 错误页 |
| 磁盘满 | `post_mortem` 抛错 | 节点级捕获 → dashboard 顶部红 banner |

### 退化

按现 graph 已有"安全默认"哲学：LLM 不可用 → 全规则；数据不全 → emotion 走"no activity history"分支 + 软提示 "📊 数据不全，结论仅供参考"；`pattern_hits` 空 → 跳过 subagents 直达 RiskGuard；`candidates` 空 → "无候选,空仓"。

### CLI 兼容

CLI exit 码语义不变（`errors` 非空 → 2；`plan is None` → 1）；CLI 走 runtime `auto-approve` 模式。

---

## 8. 测试策略

延续现仓库 `tests/` + `pytest` + `live` marker 约定。

### 后端

| 层 | 工具 | 范围 |
|---|---|---|
| 节点单测 | pytest（已存在） | 14 节点 + 4 子图，离线 fixture |
| graph e2e（合成 fixture） | pytest（已存在 `tests/fixtures/2026-04-26/`） | 整张 graph 跑通 |
| graph e2e（live） | pytest `--live`（已存在） | 真实 akshare + DeepSeek |
| GraphRuntime 单测（新） | pytest + pytest-asyncio | start/resume/edit/abort 状态机 |
| API 集成测（新） | pytest + httpx + httpx-sse | `/run` → SSE → interrupt → resume → done 全链 |
| API 契约 fuzz（新） | schemathesis | OpenAPI 契约稳定性 |

### 前端

| 层 | 工具 | 范围 |
|---|---|---|
| 组件单测 | Vitest + RTL | NodeTimeline, InterruptDrawer, EditableCell, KLineChart（mock chart） |
| store 单测 | Vitest | SSE event → store reducer |
| 类型同步 | tsc --noEmit | gen:api 后必须通过 |
| E2E happy | Playwright | mock API → click Run → SSE → review interrupt → dashboard 渲染 |

### 关键覆盖

1. interrupt 续跑全链
2. edit 重跑下游（`themes.*.phase` 改后 → 候选池变化）
3. SSE 断线重连
4. 节点错误不阻断（mock akshare 抛 RemoteDisconnected → 验证 plan 仍生成）

### CI

pre-commit：ruff + mypy + eslint + tsc + prettier + 离线 pytest + `gen:api` diff 检查。
GitHub Actions（可选）：离线套件；不跑 `--live` / Playwright。

---

## 9. 目录结构 + 工具链

### 仓库结构

```
youzi-app/
├── README.md
├── Makefile
├── pyproject.toml              # + fastapi, uvicorn[standard], sse-starlette, httpx-sse(test)
├── package.json                # root: 仅 scripts
├── .env.example
├── .gitignore                  # + apps/web/.next/, apps/web/out/, .superpowers/
├── apps/
│   ├── api/
│   │   ├── main.py             # FastAPI app + 路由
│   │   ├── graph_runtime.py
│   │   ├── editing.py          # 字段白名单 + dirty-node 依赖图
│   │   ├── routes/
│   │   │   ├── run.py
│   │   │   ├── state.py
│   │   │   ├── runs.py
│   │   │   └── kline.py
│   │   ├── sse.py
│   │   └── tests/
│   └── web/
│       ├── package.json
│       ├── next.config.mjs
│       ├── app/ components/ lib/ tests/
├── src/
│   └── youzi_agent/            # 不动；graph.py 加 3 处 interrupt(...)
├── scripts/                    # 现有
├── tests/                      # 现有跨包 e2e
├── docs/superpowers/specs/     # 本文件
├── runs/                       # 现有
└── checkpoints.db
```

### 工具链

| 工具 | 用途 |
|---|---|
| pip + venv | 后端依赖（沿用现 .venv） |
| npm | 前端 |
| Next.js 14 App Router（`output: 'export'`） | 前端框架 |
| Tailwind + shadcn/ui | 样式 |
| TanStack Query + Zustand | 状态 |
| lightweight-charts | K 线 |
| openapi-typescript | 后端 schema → TS 类型 |
| Vitest + RTL + Playwright | 前端测试 |
| ruff + mypy | Python lint/type |

### 入口命令

```makefile
install:    pip install -e .[dev] && cd apps/web && npm install
dev:        # 并行启动 uvicorn + next dev（trap SIGINT）
api:        uvicorn apps.api.main:app --reload --port 8000
web:        cd apps/web && npm run dev
gen-api:    cd apps/web && npm run gen:api
test:       pytest -q && cd apps/web && npm test
test-live:  pytest -q -m live
build:      cd apps/web && npm run build
serve:      uvicorn apps.api.main:app --port 8000   # 生产：单进程，挂 web/out/
```

### CLI 共存

`youzi-agent` 命令保留，作为 `GraphRuntime` 的薄壳（`YOUZI_AUTO_RESUME=1`）。日常无浏览器跑复盘仍可用，输出 `runs/{date}/...` 被前端历史 picker 读到。

---

## 10. 实施分期

按粒度递进，每期可独立验收。

### Phase 1 — 后端骨架
- 新增 `fastapi`/`uvicorn`/`sse-starlette` 依赖
- `apps/api/main.py` + `graph_runtime.py`（不实现 interrupt）
- `/api/run` + `/api/run/{tid}/stream` + `/api/state/{tid}` + `/api/runs` + `/api/kline/{code}`
- pytest 覆盖 runtime + 路由

### Phase 2 — 前端骨架
- `apps/web` Next.js + Tailwind + shadcn/ui 初始化
- `app/console/page.tsx` 三栏 layout（占位卡片）
- TanStack Query + Zustand store 接入
- SSE 接入：node_start/end 显示在右栏 timeline
- 中央 7 个视图（先表格 + KPI，无图表）
- 历史 picker（`/api/runs` + `/api/runs/{date}`）

### Phase 3 — Interrupt
- `src/youzi_agent/graph.py` 在 PatternMatcher/RiskGuard/TradePlanner 加 `interrupt(...)`
- runtime resume / SSE `interrupt` 事件
- 3 个 review 抽屉组件
- CLI auto-approve 模式
- e2e 测试覆盖 interrupt 全链

### Phase 4 — 编辑 / 重跑下游
- 字段白名单 + dirty-node 依赖图
- `/api/state/{tid}/edit`
- `<EditableCell>` 通用组件接入到 4 类字段
- e2e 覆盖编辑 → 重跑

### Phase 5 — 图表
- `/api/kline/{code}` + lightweight-charts 包装
- 候选池行内 sparkline
- 龙头抽屉 60 日 K 线 + 涨停标注
- 左栏 sentiment sparkline

### Phase 6 — 错误处理 + 退化 + 打磨
- SSE Last-Event-ID 续传
- interrupt 30 min auto-approve
- 数据不全软提示 banner
- 暗色主题打磨、等宽数字、表格 virtualized
- Playwright happy-path

### Phase 7 — 生产打包
- `next build && next export`
- FastAPI 挂 `apps/web/out/` 静态
- `make build && make serve` 单进程跑通

---

## 11. 开放问题 / 待研究

1. **`stream_mode` 选择**：`["updates","values"]` 是否会重复推 state？需要在 Phase 1 实测确认 SSE 事件去重策略。
2. **akshare 限频上限**：实际多并发会被禁的阈值未知；Phase 5 要打 K 线接口时跑实测确定 `Semaphore` 大小。
3. **dirty-node 依赖图维护**：v1 手写小映射；当字段编辑白名单将来扩展时，需要更系统的方式（节点声明 `reads`/`writes`），可能驱动一次 `youzi_agent` 内部重构。
4. **edit 后新 tid 与原 tid 的关系**：审计 trail 上要不要存 `parent_tid` 链路？v1 不做，但前端 history 视图最终可能需要。
5. **多 tab 同步**：用户开两个浏览器 tab 看同一日，一个改了会不会影响另一个？v1 假设不会有这种用法，不做 broadcast；v2 可以加 SSE topic broadcast。

---

## 12. 成功标准

- 浏览器打开 `localhost:8000` → 看到当日 dashboard（如已 run）或空 console（未 run）
- 点 Run → 右栏看到 14 节点流式打绿；3 节点暂停弹 review；review 后续跑
- Done → 中央候选池有内容 + 行内 sparkline + 计划在左栏；点候选池里某只股 → 龙头抽屉弹 60 日 K 线 + 涨停红三角
- 点左栏日历切到 2026-04-25 → 不重跑、直接渲染当日 snapshot
- 改 `themes.AI算力.phase: horizontal → vertical` → 候选池在 5–15 秒内重新出来
- akshare 短暂掉线 → 节点变 amber，graph 跑完，dashboard 顶上 banner 列错误

---

## 13. 不在本文件范围

- 实施步骤详单（→ 由 writing-plans skill 产出）
- 具体代码示例 / 完整 Pydantic schema / 完整 OpenAPI（→ 实施时定）
- 部署到 NAS / 公网（v1 单人本地）
- 多用户、配额、计费、安全模型（v1 非目标）
