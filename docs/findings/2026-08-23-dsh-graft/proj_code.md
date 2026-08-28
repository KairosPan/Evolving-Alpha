# 代码现状审计笔记(嫁接评估用)

## ① 分层职责与依赖方向 — 哪些是"自造框架性质"代码(嫁接候选)

依赖图(实测,自底向上,单向):L0 叶子(`schemas`/`universe`/`harness`/`llm`)← L1(`features`,`data`⇄`replay` 防火墙取数簇)← L2(`eval`)← L3(`agent` act 半环 / `refine` refine 半环)← L4(`loop` 编排)← L5(`youzi_web`,只读单向)。`harness/` 是零 intra-youzi 依赖的叶子——所有上层依赖它,它不依赖任何人。

**自造的、通用框架能给的(嫁接候选)**:
- `loop/inner_loop.py` `InnerLoop`(~380 行):日循环编排器——act→延迟打分→在线信用→熔断→refine 的调度骨架。调度本身是通用工作流;但内嵌的熔断判定/水位线/防前视断言是领域逻辑(见④,拆分时要小心)。
- `loop/compare.py` `compare_harnesses`(~170 行):多臂实验编排(factory 注入、跑臂、汇总)——典型"实验 runner",框架可替。
- `loop/run_store.py` `RunStore`:ComparisonReport JSON 原子写/逐文件容错读——通用产物存储,已被 SQLite spec C 期标记替代(`research_run/daily`)。
- `harness/snapshot.py` `SnapshotStore` + `harness/manager.py` `HarnessManager`:版本化 JSON 快照 + checkpoint/rollback——通用"版本化状态存储",SQLite spec D 期标记替代(`harness_version` 表);但 **rollback 后 rebind 语义**是领域契约,必须保留。
- `harness/edit_log.py` `EditLog`:append-only 审计日志——通用审计,D 期拆 `harness_edit` 表;但"哪些写入入 log、哪些不入"(观测 vs 编辑边界)是领域不变量。
- `llm/client.py` 重试/退避 + `llm/cache.py` `CachedLLMClient`(sha256 键录放):通用 LLM 基建,任何 LLM 框架都有对应物。
- `youzi_web/`:FastAPI+HTMX 外壳 + `registry.Feature` 插件注册表 + `data_access` 只读适配——纯展示层,可整体换。
- `data/cache.py` `PITStore`(parquet 原子写)+ `data/capture.py`(节流幂等抓取):通用"数据湖 + ingestion",但 PIT 布局(一文件=一 as-of 帧)是防火墙结构防线,spec 明确 parquet 不动。

**依赖方向铁律**:web→领域只读单向;`harness` 叶子地位(`GateSpec` 门匹配刻意放 `eval/rule_policy.py` 就为不让 harness→universe);外部依赖(akshare/openai/fastapi)全在末端且懒加载。

## ② 领域独有、任何框架给不了的(嫁接必须原样保留)

- **未来函数防火墙**(头号铁律,三重):(a) `replay/firewall.AsOfGuard` + `GuardedSource` 运行时守卫(未来日→`LookaheadError`);(b) `WalkForwardEval` 延迟打分(t 决策、游标推到 t+horizon 才打分,firewall-by-construction);(c) **结构防御**——`MarketState`/`StockSnapshot`/`CandidateUniverse` frozen 且无 source 句柄,策略拿到快照后"够不到任意日期"。已实现未来只作事后 oracle 标签,永不进决策推理路径。
- **oracle 与打分尺**(`eval/`):池成员 oracle(continued/faded/nuked + `path_outcome` stop-on-nuke)· `return_oracle`(次日开盘买→t+N 收盘卖)· `fill.py`(T+1、一字板 `fill_check` 先板块后 ST、`CostModel` 成本)· `ReturnScorer`(须 horizon≥2,`unfillable`/`missing` 一等公民)· `stats.py` C1 统计裁决(块 bootstrap CI/置换 p/MDE→`StatVerdict`)。这是"决策好不好"的领域客观尺。
- **在线信用**(`refine/credit.apply_credit`):oracle 结果→`SkillStats` Welford 直写,advantage=score−同日池基线;**每条 trajectory 只调一次**(无幂等守卫);`resolve_skill` pattern 归因 + `unattributed` 桶。
- **meta-tool 拒绝管线**(`harness/metatools.py` 9 算子 + `refine/refiner.py`):结构性编辑唯一入口,对 immutable/非法转移/越权/缺 rationale/超上限/幻觉 target/重复 id **全拒、绝不半应用、绝不崩**;退役/晋升证据门(n≥K);`write_skill` 状态钳 incubating。
- **观测 vs 编辑边界**:`SkillStats`/`Lesson.importance` 由信用直写、不入 EditLog(`_PATCH_FORBIDDEN`/`_UPDATE_FORBIDDEN` 强制);结构编辑必入 EditLog 带 rationale。
- **immutable-core**:`DoctrineEntry.__setattr__` 守卫 + `Doctrine.rewrite/remove` 双拦截,Refiner 改不动纪律红线。
- 其余领域件:regime 7 相位归一、`agent/parse` 幻觉过滤+空仓兜底、`retrieval` 预算化注入、`signatures` 失败签名。

## ③ store/SQLite 分域真相源(spec 2026-06-22,现状 = A+B-domain 已并入 main)

- **定位**:从"研究脚本+文件存储"演进为单机单人 Co-pilot 软件;新包 `youzi/store/`(领域层),标准库 `sqlite3` + WAL + 迁移 runner,单文件 `YOUZI_DB`(默认 `./data/youzi.db`),无 ORM、薄 Repository 手写 SQL、pydantic⇄行、frozen 大对象整存 JSON blob。
- **分域真相源**:运营全闭环(7 表:session→candidate→decision→fill→position→review + account_daily)= SQLite 真相源(新核心);研究产物(`research_run`+`research_daily` 逐日投影,替 RunStore,解 list() O(N),C5 聚合一句 GROUP BY)= SQLite 真相源;Harness 演化史(`harness_version`+`harness_edit` 拆表,解 EditLog 二次写放大)= SQLite 真相源;**PIT 行情 = parquet 仍是真相,DB 只存 manifest**(`pit_root/frame/ohlcv`,五态语义+covers 范围,闭合 D1);漂移时 parquet 赢,可 `pit_reindex` 重建。
- **分层精确化**:web 首次写领域数据 → 经领域窄命令 API(`OpsRepository.confirm_decision/record_fill`),"web 只读"精确化为"web 经命令 API 读+写,不触内部"。**决策路径永不持有 DB 句柄**(架构测试断言 agent/policy 构造够不到 DB);`SnapshotSource→GuardedSource→parquet` 读价格路径一行不改、不碰 manifest。
- **现状**(memory,FF `4af6b2c` 2026-06-22,495 测试):A 期地基 + B-domain(7 表 + OpsRepository + account 盈亏纯函数 + record_fill 单事务原子化/失败回滚 + 复盘/账户日快照/按打法实战胜率)已并入;⏭ B-web 录入页,再 C(研究迁移)/D(Harness 迁移)/E(PIT manifest)。跨期软链(`ops_session.harness_version`/`decision_run_ref`)B 期为可空软引用,不加 DB 级 FK。
- **对嫁接的含义**:C/D 期正是"RunStore/SnapshotStore 被替换"的既定路线——嫁接若动这些框架件,与 spec 方向一致;E 期碰 PIT 须守防火墙。

## ④ InnerLoop / compare 控制流(嫁接必须尊重的机制)

**InnerLoop.run()**(单游标、单 live H、reset-free,while 循环每交易日):
1. **act**:`engine.observe()`→`build_universe(engine.guarded_source, cursor)`→`agent.decide`;记 `EntrySnap`、draft 入 pending。
2. **延迟打分**:pending 中 `idx ≥ j+horizon` 的步,取持有路径逐日成员 `mems`,`scorer.score_step(...)` 打分(decision_mem=决策日池成员→day_baseline)。
3. **在线信用**:每个新打分步且未 frozen → `apply_credit`(恰一次)+ 记日级 advantage(空仓日 0.0;`NON_TRADE_OUTCOMES` 排除)入 `breaker_days`。**frozen 后停 apply_credit(真冻结),打分/轨迹照常。**
4. **B2 熔断**(日级武装,`breaker_days ≥ breaker_min_days` 才评估):有 `shadow_daily` → 影子配对双门(mean(diff)<−max(λσ,ε_abs) + 方向副门 ⌈k/2⌉+1 严格负日;**防前视:严格只消费 ≤ 当前已评分日的影子条目,有 assert**);无影子 → 全历史 median−c·MAD 自标定(MAD≈0 → floor_abs 兜底)。触发:回滚目标 = **退化窗起点之前**最近 checkpoint(`max(v for v,d in ckpts if d < window_start)`);首次且有目标 → `rollback_to`+`_rebind`+弃 >target 的 ckpt+清 `breaker_days` 再武装;第二次或无目标 → frozen(有目标仍先回滚)。
5. **refine 触发**:`enable_refine`(C4 消融门)AND 未 frozen AND 水位线后新增**已打分候选数**(按 outcomes 计,空仓步不算)≥ `evidence_min` AND `idx % refine_every == 0` → **先 `checkpoint(label="pre-refine …")` 记 (版本,日期)** → 证据 = `scored_steps[水位线:]`(A3 非重叠窗)+ `merge_credit_reports` 同切片 + `extract_signatures` → `Refiner.refine` → 推进水位线。次日 agent 立即看见编辑后 H。

**rebind 契约**(嫁接第一敏感点):`rollback_to` 替换 harness 对象并 rebind tools,调用方缓存的旧 `agent`/`refiner`/`mgr.tools` 引用指向废弃态 → `_rebind()` 用 **factory**(`agent_factory(mgr.harness)`,默认 `LLMAgentPolicy`)+ 重建 `Refiner(mgr.harness, llm, mgr.tools)`。**agent 必须是 factory 而非实例**;Refiner 重建清空近期编辑史是有意语义(rollback 后旧编辑史已作废)。水位线指向 run 局部 `scored_steps` 索引,与 H 版本无关,回滚后无需重置。

**compare_harnesses**(同窗同 source 同 oracle,factory 注入防交叉污染):入参全是 factory——`harness_factory()`(每臂 fresh 种子 H)、`agent_llm_factory()`/`refiner_llm_factory()`(每臂独立 client)、`store_factory()`(每臂独立快照 store)。臂:HCH(InnerLoop)/ Hexpert(冻结 H + `wf.walk()`,无 Refiner,留 Trajectory 供 C1 日级统计,不重复跑 LLM)/ Hcredit(`ablate=True`:`enable_refine=False` 的 InnerLoop,只回注战绩;无 refine→无 checkpoint→熔断只冻结不回滚,与 HCH stats 历史不对称须核对 n_breaker_trips)/ Hmin_highest/notrade(同一 wf 复用,run() 内 new ReplayEngine 无状态残留)。`shadow=True` 时**先跑 Hexpert**,其 `daily_series` 作 shadow_daily 喂 HCH 与 Hcredit 熔断(整窗含未来日,InnerLoop 内部过滤防前视)。裁决:`hch_beats_hexpert = d_excess>0`(C2 超额口径)+ C1 `StatVerdict` + C4 双通道拆分(HCH−Hcredit 编辑通道 / Hcredit−Hexpert stats 通道)。factory 调用顺序是测试契约(shadow=False:HCH→Hcredit→Hexpert;shadow=True:Hexpert→HCH→Hcredit)。

## ⑤ 离线测试架构(CI 永不触网的机制)

- **三个替身,按协议缝合**:`FakeSource`(tests/conftest.py,内存行情,实现 `MarketDataSource` 6 方法协议——与 `AkshareSource`/`SnapshotSource` 同接口,GuardedSource 照包)· `MockLLMClient`(`youzi/llm/client.py`,脚本化返回,实现 `LLMClient.complete` 协议)· FastAPI `TestClient`(web)。全部逻辑因此离线可测:466(现 495)测试零网络。
- **结构保证**:外部依赖懒加载在末端(akshare 仅 `data/source.py` 方法内 import、openai 仅 `llm/client.py` 内)——不实例化 live 类就不 import 网络库。触网只在手动 `scripts/smoke_*.py`。SQLite 测试用 `Database(":memory:")` 同样离线。
- **补充层**:`CachedLLMClient` read_only 模式(miss→`CacheMissError` 决不静默回落 live)供录放;`*_real_seeds.py` 测试用真实 57/21/22/7 种子做端到端。
- **已知盲区**:MockLLM 忽略提示 → 离线只能测"编排/对比机器"正确性,测不了 refine 实效(真实 alpha 问题必须真 DeepSeek 多日跑);离线也测不到 akshare 真实列名(`_RENAME` 须 smoke 核对)。
- **对嫁接的含义**:任何替换编排/存储的框架件,必须保持"协议注入 + 替身可插"——新组件依赖注入 `MarketDataSource`/`LLMClient`/`Scorer`/`DecisionPolicy` 协议而非具体实现,否则离线优先不变量破。

**嫁接红线清单(浓缩)**:决策路径够不到 DB/未来日期;打分必延迟;apply_credit 恰一次;结构编辑只走 meta-tool 入 EditLog、观测直写不入;rollback 后必 rebind(factory 注入,勿缓存实例);多臂必 factory 隔离;shadow 消费必按已评分日过滤;新增一切离线可测。