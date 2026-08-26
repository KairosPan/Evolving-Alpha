# ARCHITECTURE — 自进化游资系统(youzi)

> 本文件是**当前代码的结构地图**:包/模块怎么分层、谁依赖谁、运行时数据怎么流、关键类型与入口在哪。
> 它与另外两份文档分工互补,**不重复**:
> - `自进化游资系统-架构蓝图-v1.0.md` = **为什么这么设计**(论文映射、双环理论、六道闸、对抗硬化的 rationale)。
> - `CLAUDE.md` = **怎么上手操作**(命令、不变量速查、陷阱清单)。
> - 本文 `ARCHITECTURE.md` = **代码长什么样**(模块依赖图、各层职责、运行路径、对象模型、扩展点)。
>
> 依赖边由 `grep` 实测得出(非推断);截至 466 测试全绿、全离线。

---

## 1. 顶层布局

```
evolving-alpha/
├── youzi/              领域逻辑(11 个子包,零 web 依赖)        ← 本文主体
├── youzi_web/          web 层(FastAPI+HTMX,单向依赖 youzi/)
├── seeds/              种子 H:skills/memory/doctrine/state_machine.json + README
├── scripts/            手动脚本(唯一触网处 + 离线建库/起服务/造样本)
├── tests/              85 文件 / 466 测试,全离线(conftest.py 提供 FakeSource)
├── docs/
│   ├── findings/       实验记录 + 全架构评审(2026-06-09)
│   └── superpowers/    每阶段 specs/(设计)与 plans/(TDD 任务)
├── data/               PIT 快照与产物(.gitignore;非代码)
├── pyproject.toml      包定义 + pytest 配置(testpaths=tests, -q)
├── PROJECT_STATE.md · ROADMAP.md · 后续开发文档.md · 架构蓝图   权威文档
```

`youzi/` 11 个子包:`schemas` · `data` · `replay` · `features` · `universe` · `harness` · `llm` · `agent` · `eval` · `refine` · `loop`。

---

## 2. 分层依赖图(实测,自底向上;箭头 = "依赖")

```
                          ┌─────────────────────────────────────────────┐
  L5  web                 │ youzi_web/  app · registry · data_access     │
                          │           features/{research,decision}      │
                          └───────────────────────┬─────────────────────┘
                                                  │ 只读、单向
  ┌───────────────────────────────────────────────▼─────────────────────┐
  │ L4  编排顶层   loop/   inner_loop · compare · run_store               │
  │                       (依赖 agent·eval·refine·harness·llm·replay·universe)
  └───────────┬───────────────────────────────────────┬──────────────────┘
              │                                        │
  ┌───────────▼────────────┐               ┌───────────▼──────────────────┐
  │ L3  act    agent/      │               │ L3  refine   refine/          │
  │   agent·prompt·parse·  │               │   refiner·credit·signatures·  │
  │   retrieval            │               │   ops·refiner_prompt          │
  │   (→eval·harness·llm·  │               │   (→eval·harness·llm)         │
  │     universe·schemas)  │               └───────────┬──────────────────┘
  └───────────┬────────────┘                           │
              │                                         │
  ┌───────────▼─────────────────────────────────────────▼──────────────────┐
  │ L2  评测   eval/   decision·oracle·return_oracle·scorer·fill·metrics·    │
  │                    baselines·walk_forward·trajectory·stats·rule_policy   │
  │                    (→harness·replay·universe·schemas)                    │
  └───────────┬─────────────────────────────────────────────────────────────┘
              │
  ┌───────────▼───────────┐  ┌──────────────────────────────────────────────┐
  │ L1  特征   features/   │  │ L1  数据/防火墙   data/ ⇄ replay/             │
  │  echelon·blowup·       │  │  source(协议+Akshare+Guarded+Snapshot)·       │
  │  money_effect·         │  │  cache(PITStore)·snapshot_source·capture·     │
  │  sentiment·builder     │  │  calendar  ‖  firewall(AsOfGuard)·engine      │
  │  (→schemas·config)     │  │  (→schemas·features)                          │
  └───────────┬───────────┘  └───────────────────┬──────────────────────────┘
              │                                   │
  ┌───────────▼───────────────────────────────────▼────────────────────────┐
  │ L0  叶子(零 intra-youzi 依赖)                                          │
  │   schemas/(MarketState 等 frozen 快照)   harness/(H=(p,G,K,M) 活体核心) │
  │   universe/(CandidateUniverse)            llm/(LLMClient 协议+实现)      │
  └─────────────────────────────────────────────────────────────────────────┘
```

**关键架构事实**:

1. **`harness/` 是叶子** —— 这个被自进化编辑的活体状态核心 **对 `youzi/` 其它包零依赖**(只依赖 pydantic + 自己的 `regime`)。所有上层依赖它,它不依赖任何上层。`GateSpec` 的强类型门住在 `harness/skill.py`,但**门匹配逻辑刻意放在 `eval/rule_policy.py`**,就是为了不让 `harness → universe` 产生依赖。
2. **`data/` ⇄ `replay/` 小环**:`GuardedSource`(在 `data/source.py`)引用 `replay/firewall.AsOfGuard`,而 `replay/engine` 引用 `data/source` —— firewall 与 source 是一体的"防火墙取数簇"。
3. **单向 web 边界**:`youzi_web/` 对 `youzi/` **只读**,`youzi/` 永不反向依赖 web。
4. **外部依赖都在末端、且懒加载**:`akshare`(仅 `data/source.py` 方法内 import)、`openai`(仅 `llm/client.py` 内)、`fastapi`(仅 `youzi_web/`)。`pydantic`/`pandas` 贯穿;领域逻辑离线可跑。

---

## 3. 两条运行路径(运行时架构)

### 3.1 act 半环 —— 一天怎么从行情走到决策包

```
day, MarketDataSource
  │ AsOfGuard(day) 包成 GuardedSource              ……未来日 → LookaheadError(防火墙)
  ├─ universe.build_universe(gs, day)              三池(zt/blowup/dt)合成 → CandidateUniverse
  │     └ 每只 = StockSnapshot(frozen,status=limit_up/blowup/limit_down,缺失诚实 None)
  ├─ features.build_market_state(day, gs, history, as_of)
  │     └ echelon(连板梯队)+ blowup_rate + money_effect + raw_sentiment
  │       + normalize_sentiment(regime-relative,样本<60 → None) → MarketState(frozen)
  └─ agent.LLMAgentPolicy.decide(state, universe)        实现 eval.DecisionPolicy
        ├ prompt.build_system_prompt(H, injection)        把 live H=(p,K,M)+状态机渲染进系统提示
        │    └ retrieval.select_for_prompt(...)           'retrieval' 模式:相位先验∪applies_all
        │                                                  截 top-B 技能/记忆 + ≤3 孵化试验位
        ├ llm.client.complete(system, user)               DeepSeekClient(json_object+指数退避)
        │                                                  / MockLLMClient(测试)/ CachedLLMClient(录放)
        └ parse.parse_decision(raw, date, universe)       鲁棒 JSON + 幻觉 code 过滤 + 钳 confidence
                                                          → DecisionPackage(candidates / no_trade_reason)
```

### 3.2 refine 半环 —— `InnerLoop.run()` 把上面跑成 reset-free 自进化环

```
loop.InnerLoop.run()  →  LoopReport       (单游标、单 live H、reset-free)
  for 每个交易日:
    1. act        agent 用 live H 决策(同 3.1)
    2. 延迟打分   游标推进到 t+horizon,eval.scorer.score_step(...) 用已实现 oracle 打分
                  PoolScorer(池成员 SCORE) | ReturnScorer(T+1 可成交净收益,fill_check+CostModel)
    3. 在线信用   refine.apply_credit(step, H)  把 outcome 直写进 SkillStats(Welford,advantage)
                  ——观测,不入 EditLog(见 §5)
    4. 能力地板熔断  B2:影子配对差 / advantage-MAD 自标定
                  触发 → manager.rollback_to(ckpt) + _rebind(agent/refiner) + 可再武装 | frozen
    5. 每日 refine  有评分证据(水位线非重叠窗 + evidence_min)才触发:
                  manager.checkpoint() → refine.Refiner.refine(traj, credit, signatures)
                  └ 论文式 4-pass CRUD:Δp → ΔG(占位 no-op) → ΔK → ΔM
                    逐条经 harness.MetaTools 就地编辑同一 H(带 rationale 进 EditLog)
                    拒绝管线:immutable/非法转移/越权/缺rationale/超上限/幻觉target/重复id 全拒
    → 次日 agent 立即看见编辑后的 H
```

**度量对比**:`loop.compare_harnesses(...)` 用 **factory 注入**让多臂拿独立 fresh H + 独立 LLM,在**同窗同 oracle** 下并行跑:`HCH`(自精炼)/ `Hexpert`(冻结种子,无 Refiner)/ `Hcredit`(C4 消融:只回注战绩无结构编辑,`--ablate`)/ `Hmin_highest`/`Hmin_notrade`。出 `hch_beats_hexpert` + `eval.stats.StatVerdict`(bootstrap CI/p/MDE)。结果经 `loop.run_store.RunStore` 落盘供 web 看板读。

---

## 4. 包逐层参考

> 每个包:**职责** · **关键模块/类型** · **对外入口** · **它守的契约**。文件路径相对 `youzi/`。

### L0 叶子

**`schemas/`** — frozen 行情快照。
- `market.py`:`MarketState`(`as_of` 时戳 + 情绪/梯队/赚钱效应,frozen)、`EchelonRung`(连板梯队档)。
- 契约:frozen、无 source 句柄 —— 拿到它的策略**够不到任意日期**(防火墙的结构保证)。

**`universe/`** — 候选个股池。
- `stock.py`:`StockSnapshot`(frozen PIT 个股,`status`/`boards`/`seal_amount`…,缺失 None);`CandidateUniverse`(按 code 索引,`by_status`/`by_min_boards`/`by_industry`)。
- `universe.py`:`build_universe(source, day)` —— dt→blowup→zt 合成顺序保证 limit_up 优先覆盖。
- 契约:dup code → `ValueError`;`CandidateUniverse.__bool__=True`(杀 falsy-empty)。

**`harness/`** — **被自进化编辑的活体状态 `H=(p,G,K,M)`**(见 §5 对象模型)。零 intra-youzi 依赖。
- `harness.py` `HarnessState`(p/K/M/cycle 容器 + to_dict/from_dict)· `doctrine.py` `Doctrine`/`DoctrineEntry`(immutable 守卫)· `skill.py` `Skill`/`SkillStats`/`GateSpec`(4 态生命周期)· `memory_item.py` `Lesson`/`Importance`(双衰减)· `memory_store.py`/`registry.py`(索引+CRUD+写保护)· `cycle.py` `StateMachine`(7 相位 G_cycle 种子)· `regime.py`(7 canonical 相位归一)。
- 编辑面:`metatools.py` **9 个 meta-tool** + `edit_log.py` `EditLog`(append-only 审计)。
- 持久化:`snapshot.py` `SnapshotStore`(版本化 JSON,原子写)· `manager.py` `HarnessManager`(checkpoint/rollback_to + rebind tools)· `loader.py` `load_seeds(dir)`。

**`llm/`** — LLM 适配。
- `client.py`:`LLMClient`(协议,`complete(system,user)→str`)/ `MockLLMClient`(脚本化)/ `DeepSeekClient`(OpenAI 兼容,json_object + 指数退避重试,openai 懒加载)。
- `cache.py`:`CachedLLMClient`(read_write/read_only/off 三模,key=sha256(model+temp+system+user+fingerprint),read_only miss 即 `CacheMissError` 决不静默回落 live)。
- `extract.py`:`extract_json_object`(配平括号,容 thinking/markdown 前缀)。

### L1 特征 / 数据

**`features/`** — 纯函数算特征 → 组装 `MarketState`。
- `echelon`(连板梯队 + max_board_height)· `blowup`(炸板率)· `money_effect`(昨涨停今表现)· `sentiment`(`raw_sentiment` 加权 + `normalize_sentiment` 滚动百分位,样本<`SENTIMENT_MIN_SAMPLES`=60 → None)· `builder.build_market_state`(组装,只读 ≤cursor)。

**`data/` + `replay/`** — 防火墙取数簇。
- `data/source.py`:`MarketDataSource` 协议;`AkshareSource`(live,`daily_ohlcv` 走 `_fallback_ohlcv` eastmoney→sina→tencent 三源 + `_retry_ak`)· `GuardedSource`(包一层 `AsOfGuard`,池/OHLCV 查询守 ≤as_of)· `_RENAME`(akshare 列名映射 —— **真实列名须 smoke 核对**)。
- `data/cache.py` `PITStore`(per-(kind,day) 池 parquet + per-code OHLCV + calendar,**原子写 temp+os.replace**)· `data/snapshot_source.py` `SnapshotSource`(离线读 store,实现协议,缺池报错/缺OHLCV返空)· `data/capture.py` `capture_window`(节流幂等预取 akshare→store)· `data/calendar.py`。
- `replay/firewall.py`:`AsOfGuard.check/advance`(单调,未来 → `LookaheadError`)· `replay/engine.py` `ReplayEngine`(cursor/observe/step/reset_to,reset-free,history 侧信道防泄漏)。

### L2 评测 `eval/`

策略量化的统一尺。所有策略都是 `DecisionPolicy`,统一进 `WalkForwardEval`。
- `decision.py`:`Candidate` / `DecisionPackage`(frozen)/ `DecisionPolicy` 协议。
- `oracle.py`:池成员 oracle —— `outcome`(continued/faded/nuked)、`path_outcome`(持有路径 + stop-on-nuke + `nuke_index`)、`DayMembership`、`NON_TRADE_OUTCOMES`(unfillable/missing)、`SCORE` 映射。
- `return_oracle.py`:`forward_return`(次日开盘买→t+N 收盘卖)/ `ReturnOracle`。
- `fill.py`:`CostModel`(佣金 3bp×2 / 印花税卖侧 5bp / 滑点 30bp)· `limit_threshold`(先板块后 ST)· `fill_check`(一字板/开盘顶板/正常,比值判定不绝对取整)。
- `scorer.py`:可插拔 `Scorer` 协议 —— `PoolScorer`(默认,取 `mems[-1]`,回归安全)/ `ReturnScorer`(T+1 净收益,`unfillable`/`missing` 一等公民不丢弃,**须 horizon≥2**)。
- `metrics.py`:`ScoredCandidate` / `EvalReport`(双口径 `mean_score`[filled] vs `mean_score_all_in` + `fill_rate`/`n_unfillable`/`n_missing` + by_pattern)。
- `walk_forward.py`:`WalkForwardEval`(**延迟打分**:t 决策、t+horizon 才打分,**firewall-by-construction**)+ `walk()→Trajectory`。
- `trajectory.py`:`Trajectory`/`TrajectoryStep`/`EntrySnap`(frozen 观测轨迹;尾部不足 horizon 的步 `scored=False`)。
- `stats.py`:**C1 统计裁决** —— `daily_series`/`paired_daily_diff`/`moving_block_bootstrap`(CI)/`sign_permutation_pvalue`/`mde` → `StatVerdict ∈ {win,loss,flat,insufficient}`(配对日<8 → insufficient)。
- `baselines.py`:`NoTradePolicy`/`HighestBoardPolicy`(=Hmin floor)/`PoolAveragePolicy`/`RandomFromPoolPolicy`。
- `rule_policy.py`:`HarnessRulePolicy`(真读 live H 的 `GateSpec` 门、零 LLM)+ `gate_matches`。

### L3 act / refine

**`agent/`** — act 半环(见 §3.1)。`agent.py` `LLMAgentPolicy` · `prompt.py`(H→提示,full/retrieval 注入)· `retrieval.py` `select_for_prompt`(预算化检索 + 孵化试验位)· `parse.py`(幻觉过滤 + 兜底空仓)。

**`refine/`** — refine 半环。
- `refiner.py`:`Refiner.refine(traj, credit, signatures)→RefineReport` —— 4-pass CRUD + 退役/晋升证据门(`min_retire_samples`/`min_promote_samples`)+ 拒绝管线。
- `credit.py`:`apply_credit`(oracle→`SkillStats`,Welford,`expectancy`=advantage / `expectancy_raw`=原始分双账)· `CreditReport`/`SkillCredit`· `resolve_skill`(pattern→技能,strip+casefold)· `merge_credit_reports`(只读合并)。
- `signatures.py`:`extract_signatures`(board-rank×outcome 四类入场失败签名)。
- `ops.py`:`RefineOp`/`PassKind`/`PASS_TOOLS`(白名单)/`parse_ops`· `refiner_prompt.py`(各 pass 系统/证据提示 + 涉案技能全文 + 近 2 次编辑史)。

### L4 编排 `loop/`

`inner_loop.py` `InnerLoop`(§3.2)+ `LoopConfig`/`RefineEvent`/`BreakerEvent`/`LoopReport` · `compare.py` `compare_harnesses`(多臂 + factory 注入 + 影子地板)+ `ArmReport`/`ComparisonReport` · `run_store.py` `RunStore`(原子写 ComparisonReport JSON,逐文件容错读)。

### L5 web `youzi_web/`(单向依赖 youzi/,纯离线)

- `app.py`:`create_app()`(FastAPI + Jinja ChoiceLoader 多模板目录 + 静态挂载 + home 落首个 enabled 子页)。
- `registry.py`:`Feature`/`SubNavItem` + `FEATURES` 注册表 —— **加功能=append 一个 Feature + 新 `features/<name>/` 模块,外壳零改**。
- `data_access.py`:对 `youzi/` **只读** —— `seed_harness`/`snapshot_harness`/`harness_view`(算 hit_rate/nuke_rate)、`list_runs`/`load_run`(`YOUZI_RUNS_DIR`)、`skill_plan`(pattern→种子 H 技能计划)。
- `features/research/`(🔬 H 查看器 / 三方对比 / refine 时间线 / trajectory,一份 `ComparisonReport` 驱动)· `features/decision/`(🎯 决策驾驶舱,离线渲染已存决策 + join 技能计划)。

---

## 5. Harness `H=(p,G,K,M)` 对象模型(跨文件的核心)

| 符号 | 实现 | 内容 | 编辑算子(meta-tool) |
|---|---|---|---|
| **p** doctrine | `Doctrine`/`DoctrineEntry` | 分相位作战指导 + `immutable=True` 纪律红线 | `rewrite_doctrine` |
| **G** 子 Agent | (目前只有主 Agent) | Refiner 的 ΔG-pass 是**占位 no-op**;G 群是 Phase-1+ | (保留) |
| **K** 技能库 | `SkillRegistry` / `Skill` / `SkillStats` / `GateSpec` | 57 种子技能(pattern/failure_detector/feature),4 态生命周期 | `write/patch/retire/revive/promote_skill` |
| **M** 复盘记忆 | `MemoryStore` / `Lesson` / `Importance` | 21 种子记忆(principle/loss),双衰减权重 | `process/update/demote_memory` |
| 周期状态机 | `StateMachine`(`cycle.py`) | 7 相位 G_cycle 种子 + transitions | (只读种子) |

- **技能生命周期**:`incubating →(promote,证据门 n≥3 且均值>0)→ active`;`dormant ↔ incubating(revive)`;`retired`(终态)。非法转移 → `InvalidTransitionError`。
- **观测字段**(`SkillStats`: n/wins/losses/nukes/ewma/expectancy;`Lesson.importance`)**由信用直写、不可经 meta-tool 改**(`registry._PATCH_FORBIDDEN` / `memory_store._UPDATE_FORBIDDEN` 强制)。
- 载入:`load_seeds(seeds/)`;持久化/回滚:`HarnessManager.checkpoint(label)→version` / `rollback_to(version)`(重 bind tools)。

---

## 6. 横切不变量(架构级 — 操作清单见 `CLAUDE.md`)

1. **未来函数防火墙**:决策只用 ≤t(`GuardedSource`/`AsOfGuard`);打分延迟到 t+horizon(`WalkForwardEval`);已实现未来只作事后 oracle 标签,绝不进决策推理路径;frozen 无 source 句柄的快照是结构防御。
2. **观测 vs 编辑边界**:`SkillStats`/`importance` 由 `apply_credit`/`demote` 直写(观测,不入 EditLog);结构性编辑只走 9 个 meta-tool 入 `EditLog`。
3. **immutable-core 写保护**:`DoctrineEntry.__setattr__` 守卫 + `Doctrine.rewrite/remove` 双拦截;Refiner 改不动纪律红线。
4. **领域/web 单向**:`youzi_web/ → youzi/` 只读,永不反向。
5. **离线优先**:逻辑全离线可测(`FakeSource`/`MockLLMClient`/`TestClient`);live 适配器(akshare/DeepSeek)是末端可换件。

---

## 7. 持久化与磁盘产物

| 产物 | 写者 | 布局 | 读者 |
|---|---|---|---|
| PIT 快照 | `data/capture.capture_window` | `<root>/{zt,prev,blowup,dt}/YYYYMMDD.parquet`、`<root>/ohlcv/<code>.parquet`、`<root>/calendar.parquet`(原子写) | `data/snapshot_source.SnapshotSource`(`YOUZI_SNAPSHOT`) |
| Harness 快照 | `harness/snapshot.SnapshotStore` | `<dir>/snap_NNNN.json` = {version,label,harness,log}(原子 tmp→rename) | `HarnessManager.rollback_to` |
| 对比 run | `loop/run_store.RunStore` | `<YOUZI_RUNS_DIR>/<run_id>.json`(默认 `runs/`) | web `data_access.load_run` |
| 种子 H | (人工/抽取) | `seeds/{skills,memory,doctrine,state_machine}.json`(schema 见 `seeds/README.md`) | `harness/loader.load_seeds` |

---

## 8. 扩展点(怎么加东西不破不变量)

- **加一个策略** → 实现 `eval.DecisionPolicy.decide(state, universe)→DecisionPackage`,即可进 `WalkForwardEval`/`compare_harnesses`。
- **加一个 oracle/打分口径** → 实现 `eval.Scorer` 协议(`score_step(...)`),由 `WalkForwardEval`/`InnerLoop`/`compare` 注入;注意 T+1(`ReturnScorer` 须 horizon≥2)。
- **加一个进化算子** → 在 `harness/metatools.py` 加 meta-tool(进 EditLog、带 rationale、守观测字段写保护),并在 `refine/ops.PASS_TOOLS` 对应 pass 注册。
- **加一个数据源** → 实现 `data.MarketDataSource` 协议(6 方法),套 `GuardedSource` 即享防火墙;live 源把网络/重试关在方法内。
- **加一个 web 功能** → 新 `youzi_web/features/<name>/`(router+service+templates),在 `registry.FEATURES` append 一个 `Feature`,外壳零改;对 `youzi/` 保持只读。

---

## 9. 测试架构

- 全 466 测试**离线**:`tests/conftest.py` 的 `FakeSource`(内存行情,实现 `MarketDataSource` 协议)+ `MockLLMClient`(脚本化 LLM)+ FastAPI `TestClient`(web)。
- 触网只在手动脚本:`scripts/smoke_akshare.py`(核列名)、`scripts/smoke_deepseek_agent.py`、`scripts/smoke_compare.py`。**CI/测试永不触网。**
- 真实种子端到端:多个测试(`*_real_seeds.py`)直接 `load_seeds(seeds/)` 验证载入/编辑/对比在真实 57/21/22/7 种子上成立。
