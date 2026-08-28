# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目是什么

把论文《Continual Harness》(2605.09998) 的两环自进化机制 `H=(p,G,K,M)`,落到 A 股**游资/超短**交易(《轮回.docx》playbook),做一个**会自己改打法**的 **决策辅助 Co-pilot**——系统出排序候选 + 计划 + 理由,**人确认下单,绝不自动交易**。

中心问题(尚未回答):**自进化(每日精炼 H)能否产生 alpha——`HCH`(自精炼)能否跑赢 `Hexpert`(冻结种子)?** 自进化机器与评测尺都已建成、466 测试全绿且全离线;真实多窗收益对比待 off-peak 建库后跑。

- 栈:Python 3.12 · `akshare`(A 股数据,免费)· `DeepSeek` API(OpenAI 兼容,`deepseek-chat`/`deepseek-reasoner`)· `pydantic` v2 · `pandas`/`pyarrow` · web 用 `FastAPI`+`Jinja2`+`HTMX`。
- 两个包:`youzi/`(领域逻辑,零 web 依赖)+ `youzi_web/`(web 层,单向依赖 `youzi/`)。

## 先读这些(权威文档 — 勿在本文件重复其内容)

| 文档 | 作用 |
|---|---|
| `PROJECT_STATE.md` | 一页纸"压缩上下文":全部关键状态 + 每阶段进度/债务。**新会话先读这份。** |
| `ROADMAP.md` | 总图:在造什么、走到哪、下一步;评审五根因 + 波次路线图。 |
| `后续开发文档.md` | 开发交接:模块地图 + §2 核心不变量 + §3 工作流 + §5 债务清单。 |
| `ARCHITECTURE.md` | **当前代码结构地图**:分层依赖图(实测)/ 运行路径 / 包逐层参考 / 对象模型 / 扩展点。 |
| `自进化游资系统-架构蓝图-v1.0.md` | **权威设计源**(11 节):主映射表/双环/子系统详设/六道闸/术语。 |
| `docs/findings/` | 实验记录(如真实数据 HCH 退化结论、2026-06-09 全架构评审 + 16 提案)。 |
| `docs/superpowers/{specs,plans}/` | 每阶段的 spec(设计)与 plan(TDD 任务),按 `YYYY-MM-DD-<topic>` 命名。 |
| `seeds/README.md` | 种子 H 的 schema + 相位归一词表 + v1 已知缺口。 |

## 环境与常用命令

```bash
# 一次性 setup(虚拟环境已在 .venv/,Python 3.12)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"                  # akshare/pandas/pydantic/pyarrow/openai/pytest
pip install -r requirements-web.txt      # web 用:fastapi/jinja2/uvicorn/httpx

# 测试(466 个,全部离线 — FakeSource/MockLLMClient/TestClient,永不触网)
.venv/bin/python -m pytest                       # 全量(pyproject 已配 -q)
.venv/bin/python -m pytest tests/test_refiner.py # 单文件
.venv/bin/python -m pytest tests/test_refiner.py::test_xxx   # 单测试
.venv/bin/python -m pytest -k "credit and not integration"   # 关键字筛选

# 起 web(研究 + 决策驾驶舱):http://127.0.0.1:8000
python scripts/sample_run.py             # 先离线造一个样本 run(MockLLM+FakeSource)→ runs/sample.json
python scripts/serve_web.py              # uvicorn dev server(reload)

# 触网脚本 — 仅手动,CI/测试永不触网。需 DEEPSEEK_API_KEY(用户提供,勿存进库)
python scripts/smoke_akshare.py <YYYYMMDD>           # 核对 akshare 真实列名(见下方陷阱)
DEEPSEEK_API_KEY=... python scripts/smoke_deepseek_agent.py <YYYYMMDD>   # 单日真实 LLM 选股
DEEPSEEK_API_KEY=... python scripts/smoke_compare.py <start_ymd> <end_ymd> [horizon] [temp] [pool|return] [--ablate]
# 例: DEEPSEEK_API_KEY=sk-... python scripts/smoke_compare.py 20240601 20240607 2 0.0 return

# 建 PIT 快照(唯一碰 akshare 的可离线复用步骤;慢、节流 0.3s/调用、幂等可续跑)
python scripts/capture_window.py <start_ymd> <end_ymd> <out_dir>
# 之后离线无限跑: YOUZI_SNAPSHOT=<out_dir> DEEPSEEK_API_KEY=... python scripts/smoke_compare.py <s> <e> 2 0.0 return
```

**环境变量**:`DEEPSEEK_API_KEY`(真实 LLM)· `YOUZI_SNAPSHOT`(设了则用 PITStore 离线源,零 akshare)· `YOUZI_RUNS_DIR`(run-store 落盘目录,默认 `runs/`)。

## 架构大图(需读多文件才懂的部分)

### 单向分层数据流(领域)

```
akshare/PIT 快照
   └─ data/source.py  MarketDataSource 协议
        AkshareSource(live,OHLCV 三源 fallback) / SnapshotSource(离线) / FakeSource(测试)
   └─ data/source.GuardedSource  ← replay/firewall.AsOfGuard 把关 ≤t(未来日 → LookaheadError)
        └─ universe/  build_universe → CandidateUniverse(三池合成的 frozen 个股快照)
        └─ features/  build_market_state → schemas/market.MarketState(frozen,regime-relative 情绪)
             └─ agent/  LLMAgentPolicy.decide(state, universe) → eval/decision.DecisionPackage
                  (act 半环:把 live H 渲染进 system prompt,调 LLM,鲁棒 parse + 幻觉过滤)
   └─ eval/  WalkForwardEval 延迟打分(t 决策、t+horizon 才用已实现 oracle 打分)
        oracle(池成员 continued/faded/nuked)· scorer(PoolScorer/ReturnScorer 可成交净收益)
        · stats(C1 bootstrap CI + StatVerdict)· baselines
```

### 自进化内环(refine 半环 — 这是项目的核心)

`loop/inner_loop.InnerLoop.run()` 把上面跑成一个 **reset-free 交错环**:
**每个交易日 → act(用 live H 决策) → 延迟打分 → 在线信用(`refine/credit.apply_credit` 把 oracle 结果直写进 `SkillStats`) → 能力地板熔断(B2:影子配对差/MAD 自标定,触发则 rollback+rebind 或 frozen) → 每日 refine(`refine/refiner.Refiner.refine` 论文式 4-pass CRUD:Δp→ΔG→ΔK→ΔM,经 9 个 meta-tool 就地编辑同一 H,次日 agent 立即可见) → 下一日**。

`loop/compare.compare_harnesses(...)` 把多臂放上**同窗同 oracle**的尺对比:`HCH`(自精炼)vs `Hexpert`(冻结种子 H,无 Refiner)vs `Hcredit`(C4 消融:只回注战绩、无结构编辑,`--ablate`)vs `Hmin_*`(裸基线)。**factory 注入**让每臂拿独立 fresh H + 独立 LLM,杜绝交叉污染。出 `hch_beats_hexpert` + C1 `StatVerdict`。

### Harness `H=(p,G,K,M)`(被自进化编辑的活体状态,`harness/`)

`p`=doctrine(`Doctrine`)· `K`=技能库(`SkillRegistry`,4 态生命周期)· `M`=复盘记忆(`MemoryStore`,双衰减 importance)· 情绪周期状态机(`StateMachine`,G_cycle 种子)。**G(子 Agent 群)目前只有主 Agent,Refiner 的 ΔG-pass 是占位 no-op。** 载入种子见 `harness/loader.load_seeds`;持久化/回滚见 `harness/{snapshot,manager}`(`HarnessManager.checkpoint/rollback_to`)。

## 不可动摇的不变量(改任何东西都要守 — 多次终审都在守这些)

1. **未来函数防火墙(头号铁律)**。决策时刻的代码只能用 ≤t 信息。取数一律经 `GuardedSource`(`AsOfGuard.check(day)`,未来日 → `LookaheadError`);打分用**延迟打分**(`WalkForwardEval`:t 决策、游标推进到 t+horizon 才打分);"已实现未来"oracle/teacher 的未来标签**只进打分/训练,永不进决策推理路径**。防御还来自**结构**:`MarketState`/`StockSnapshot`/`CandidateUniverse` 是 frozen、无 source 句柄的快照——拿到它的策略**够不到**任意日期。注意:`GuardedSource.trading_calendar()` 故意不设防(日期表非价格);`daily_ohlcv` 只守 `end≤as_of`,`start` 可任意早。
2. **观测 vs 编辑边界**。`SkillStats`(n/wins/losses/nukes/ewma/expectancy)与 `Lesson.importance` 是**观测**——由 `refine.apply_credit`/`MemoryStore.demote` 按已实现 oracle 直写,**不算结构性编辑、不入 EditLog**(`registry._PATCH_FORBIDDEN`/`memory_store._UPDATE_FORBIDDEN` 强制)。**结构性编辑(改打法)只能经 `harness/metatools.py` 的 9 个 meta-tool**(write/patch/retire/revive/promote_skill · process/update/demote_memory · rewrite_doctrine),且进 `EditLog` 审计带 `rationale`。
3. **immutable-core 写保护**。`DoctrineEntry.immutable=True` 的纪律红线由 `__setattr__` 守卫 + `Doctrine.rewrite/remove` 双重拦截,Refiner 永远改不动。(反序列化经 `model_validate` 绕过守卫重建是有意的;守卫只防构造后改写。)
4. **领域/web 分层**。`youzi/`(领域)零依赖 web;`youzi_web/`(web)**单向**依赖领域、对 `youzi/` 只读。加 web 功能 = append 一个 `youzi_web/registry.Feature` + 新 `features/<name>/` 模块,外壳零改。
5. **离线优先**。全部逻辑离线可测:测试用 `FakeSource`(行情)/`MockLLMClient`(LLM)/`TestClient`(web),永不触网。真实 akshare/DeepSeek 只在 `scripts/smoke_*.py`(手动)。**新增任何东西都必须保持离线可测。**

## 代码约定(照抄现有风格)

- **pydantic 模型分三类**:PIT 快照 = `frozen=True`;种子载入 = `extra="forbid"`(catch 拼写错);可被 patch 的 = `validate_assignment=True`。
- **容器类**(`SkillRegistry`/`MemoryStore`/`CandidateUniverse`/`EditLog`)一律 `__bool__ = True`,杀 falsy-empty 陷阱(曾两次中招)。
- **缺失值诚实 `None`,不臆造 0/""**;用 `pd.isna(v)` 判缺(含 NaT)。
- **regime 归一**:`harness/regime.py` 把不统一的相位词归一到 **7 个 canonical 相位**(`混沌冰点/修复启动/情绪回暖/题材启动/主升/震荡补涨/退潮`)+ 正交**生态标签**,在 `from_seed` 时一次性完成。
- **LLM 输出一律不可信**:`agent/parse.py` 过滤幻觉 code(只留 universe 内的)、钳 confidence、malformed → 空仓兜底;`Refiner` 拒绝管线对 immutable/非法转移/越权/缺 rationale/超上限/幻觉 target/重复 id **全拒、绝不半应用、绝不崩**。
- **DecisionPolicy 协议**:所有策略(含 LLM Agent、`HarnessRulePolicy`、baselines)都实现 `decide(state, universe) → DecisionPackage`,统一进 `WalkForwardEval` 量化。

## 开发工作流与 git

每个阶段一个完整循环:**brainstorm → spec(`docs/superpowers/specs/`) → plan(`docs/superpowers/plans/`,bite-sized TDD 任务) → subagent-driven 实现(按层 bundle、per-task commit) → 两段评审(① spec 合规 ② 代码质量对抗) → opus 终审(集成级:不变量/防火墙/真实数据鲁棒性) → FF 合并**。每阶段更新 `PROJECT_STATE.md` + memory。

- **git**:`main` 受保护;功能在 `phase-xx` / 主题分支做;commit message 中文,按 `feat/fix/refactor/test/docs/chore` 分类(看 `git log` 既有风格)。完成 → 验证 merged main 全绿 → FF 合并 → 删分支。
- 不变量靠评审守:评审历史抓下的真问题样本——falsy-empty-log 静默丢弃、`__setattr__` 绕过 immutable、NaT→"None" 字符串、半改污染、幻觉 code、未来函数侧信道泄漏。**这些不是走过场。**

## 高频陷阱(动手前知道,省一轮终审)

- **akshare 真实列名未核对**:离线测试测不到列名。跌停池封单列是 `封单资金`≠`封板资金`;zt 池可能 `最后封板时间`≠`首次封板时间`。依赖个股字段前先跑 `scripts/smoke_akshare.py <真实交易日>` 核对并修 `data/source.py` 的 `_RENAME`。
- **幸存者偏差未解**:akshare 概念成分是**当前**成分;退市/ST/改名/当时可交易池未处理。**当前防火墙只防日期 lookahead,不防 survivorship**——别误以为绿灯=survivorship-safe。
- **MockLLM 忽略提示**:离线测试测的是"对比机器/编排机器"的正确性,**测不了 refine 实效**。真实"自进化是否胜 frozen"必须真实 DeepSeek 多日跑。
- **ReturnScorer 要 horizon≥2**:T+1 合规——`entry==exit` 会 raise(次日开盘买→t+N 收盘卖)。默认 horizon=1 只能配 `PoolScorer`。两个 scorer 是不同 oracle 语义,混用会改 outcome 分布。
- **rollback 后别用旧引用**:`HarnessManager.rollback_to()` 会 rebind tools;调用方缓存的旧 `mgr.tools`/`harness` 指向回滚前状态且静默操作废弃态。`InnerLoop` 经 `_rebind`/factory 解此债务——自己写编排时照做。
- **`apply_credit` 每条 trajectory 只调一次**:Welford 累计,重复调会重复累加 stats(无幂等守卫)。
- **OHLCV 端点会硬拒连**:`AkshareSource.daily_ohlcv` 走 eastmoney→sina→tencent 三源 fallback(全挂才 loud)。建库撞限流就 off-peak 重跑(`capture_window` 幂等续跑)。
- **种子是 v1 草稿**(~65% 覆盖《轮回》):skills/memory/doctrine/state_machine 有已知缺口(`seeds/README.md`),正是 Refiner 该自己补的。`HarnessRulePolicy` 用的 `GateSpec` 强类型门目前仅测试种子填充。
