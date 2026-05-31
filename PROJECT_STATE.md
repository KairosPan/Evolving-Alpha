# PROJECT_STATE — 自进化游资系统(上下文压缩 / 开发交接)

> 本文件是 session 的"压缩上下文":一页纸记住项目全部关键状态,使会话可被压缩/重启而不丢线索。新会话先读本文件 + `自进化游资系统-架构蓝图-v1.0.md`。

## 1. 项目身份
- **目标**:把论文《Continual Harness》(2605.09998)的 `H=(p,G,K,M)` 两环自进化机制,落到 A 股**游资/超短**交易(《轮回.docx》playbook),做一个**会自己改打法**的系统。
- **定位边界**:**决策辅助 Co-pilot**(系统出排序候选+计划+理由,**人确认下单**,不自动下真单)。
- **进化数据**:历史回放为主训练 + 实盘复盘在线适配。**四层全进化**(K 模式库+选股子Agent、周期/情绪分类器、记忆/复盘 M、模型权重 θ + Harness 提示 p)。

## 2. 已锁定的架构决策(详见蓝图)
- **方案 A(Continual Harness 直译)= 目标态;方案 B(Harness-only 冻结模型)= MVP/Phase-1;方案 C(锦标赛/进化算法)= 吸收为 K/G 的孵化—选择机制(育种场)。**
- **H=(p,G,K,M)**:`p`=作战 doctrine;`G`=游资子Agent群(周期分类器/龙头接力/题材挖掘/预期差/风控止损/复盘/公告监管否决/fill-feasibility);`K`=葵花宝典+模式/特征技能库(带滚动胜率+oracle_gap);`M`=复盘知识库(regime×模式×结果 索引,带 decay)。
- **双环**:inner=每日收盘复盘 Refiner 四遍 CRUD(Δp,ΔG,ΔK,ΔM),reset-free;outer=回放跑 π_θ → PRM 过程奖励 → frontier teacher + **已实现未来 oracle** relabel → soft-SFT/LoRA。**episode=一个完整周期轮回**(冰点→主升→退潮→冰点)。
- **交易 vs Pokémon 三差异**:① 有完美 oracle=已实现的未来(↔Dijkstra);② oracle 会漂移(alpha decay);③ 对抗反身。→ **非平稳六道闸**:regime 标签 + decay 加权 + dormant 技能"轮回"复活 + alpha-decay 监控 + 能力地板回退 + OOS/影子盘/PIT 防前视。

## 3. 对抗评审硬化(已纳入蓝图,务必保留)
- **P0**:① 未来函数防火墙(PRM/G 推理只用 ≤t;oracle/teacher 的未来标签只进训练集,永不进实盘推理路径)② 状态 SSOT(相位/情绪在 `s_t` 侧、客观可审计、**per-题材线向量+全局母状态**;G 只读不写定义;情绪值 regime-relative 归一化,弃绝对阈值)③ frozen-doctrine 影子对照 + 能力地板熔断 ④ PIT 数据治理(退市/ST/停牌/改名/当时可交易池,根除幸存者偏差)。
- **P1**:⑤ 仓位/组合/相关性层 + 止损器机制 ⑥ fill-feasibility(涨停买不进)+ 公告/监管 hard 否决器 ⑦ 交易版 oracle 度量 `oracle_gap`(完美后见之明最优买卖点 vs 实际)。
- **P2**:⑧ 集中精炼 + master_龙头_agent 分派 ⑨ M regime 时戳+decay+dormant 复活(**放弃"单调累积"**)⑩ 防坑结构/出货分时 codify 成可执行失败检测技能 + 涌现技能审计闸 ⑪ θ 版本管理/影子/回滚。

## 4. 技术栈(本 session 决定)
- **语言**:Python。**数据源**:`akshare`(免费 A 股数据)。**Agent/Refiner LLM**:**DeepSeek API**(OpenAI 兼容,`base_url=https://api.deepseek.com`,模型 `deepseek-chat`=V3 / `deepseek-reasoner`=R1)。
- **akshare 核心函数(已核实)**:`stock_zh_a_hist`(日线 OHLCV,adjust=qfq)、`stock_zt_pool_em`(涨停股池:代码/名称/连板数/炸板次数/涨停统计/最后封板时间/所属行业)、`stock_zt_pool_previous_em`(昨日涨停今表现)、`stock_zt_pool_strong_em`、`stock_zt_pool_zbgc_em`(炸板池)、`stock_zt_pool_dtgc_em`(跌停池)、`stock_lhb_detail_em`(龙虎榜)、`stock_board_concept_name_em`/`stock_board_concept_cons_em`(概念板块+成分)、`tool_trade_date_hist_sina`(交易日历)、`stock_individual_info_em`、`stock_zh_a_spot_em`。
- **注意**:akshare 概念板块成分是**当前**成分(非 PIT)→ Phase-0 须"边跑边快照"积累 PIT;历史成分/退市票需 best-effort,记为已知限制。

## 5. 落地 Roadmap 与当前里程碑
- **Phase-0(当前)**:PIT 数据治理 + reset-free 回放引擎(含未来函数防火墙)+ 种子注册表(K/M/p schema)+ Hmin/Hexpert 基线。**首个执行计划聚焦 Phase-0a:数据·特征·回放地基**(见 `docs/superpowers/plans/`)。
- Phase-1(=B):冻结 DeepSeek + inner-loop Refiner + co-pilot 决策包,端到端跑通,OOS 上优于 Hexpert 静态版。
- Phase-2(=A):接 outer loop(PRM+oracle relabel+LoRA)+ C 育种场。
- Phase-3:实盘小资金 HITL 灰度。

## 6. 仓库与文件地图
- `自进化游资系统-架构蓝图-v1.0.md` — **完整蓝图(权威设计源)**,11 节 + 附录,含主映射表/双环图/子系统详设/六道闸/术语表。
- `轮回.docx` — 游资 playbook 源(文本已转 `/tmp/lunhui.txt`,1715 行)。
- `2605.09998v1.pdf` — Continual Harness 论文源(文本已转 `/tmp/paper.txt`,28 页;关键机制在 §2.2/§3.1-3.3/§4.5-4.6)。
- `PROJECT_STATE.md` — 本文件。
- git:已 `init`(main 分支,首提交 `77b615c`),`.gitignore` 忽略 macOS 垃圾/`.claude/settings.local.json`/数据产物。`core.quotepath=false`。
- 31MB 的源 PDF 在 git 历史里(本地无碍;推远程想精简可转 git-lfs 或 untrack)。

## 7. 进度与下一步

### Phase-0a 已完成 ✅(branch `phase-0a-data-replay`)
数据·特征·回放地基已实现:`youzi/{schemas,data,features,replay}/` + 31 个离线测试全绿。两段评审 + 终审通过,**未来函数防火墙端到端 SOUND**(终审追了 6 条数据通道无泄漏;曾发现并修复 `reset_to` 的 history 侧信道泄漏,已加回归测试)。
- 模块:`schemas/market.py`(frozen MarketState/EchelonRung)· `replay/firewall.py`(AsOfGuard/LookaheadError)· `data/source.py`(MarketDataSource 协议+AkshareSource+GuardedSource)· `data/{calendar,cache}.py`(PITStore)· `features/{echelon,blowup,money_effect,sentiment,builder}.py` · `replay/engine.py`(ReplayEngine:cursor/observe/step/reset_to,reset-free)。
- 测试离线(FakeSource);akshare 仅由手动脚本 `scripts/smoke_akshare.py <YYYYMMDD>` 触网。

### Phase-0b 进行中
- **种子知识库 v1 已抽取并入 main** → `seeds/{skills,memory,doctrine,state_machine}.json`(57技能/21记忆/22doctrine(10纪律红线)/7相位;`seeds/README.md` 有 schema+相位归一词表+v1 缺口)。
- **Phase-0b-1 已完成并入 main**(`youzi/harness/`:regime 归一 / Skill+decay 统计 / Lesson+双衰减 / Doctrine(immutable核)/ 状态机 / registry / store / HarnessState / loader):只读载入+查询,**载入真实 seeds 集成测试通过**(57/21/22/7,10纪律红线,全部相位归一干净);61 测试绿,subagent-driven 两段评审+终审 READY。
- **Phase-0b-2 已完成并入 main**(`youzi/harness/{errors,edit_log,metatools}.py` + 容器 CRUD):可编辑 Harness——9 个 meta-tools(write/patch/retire→dormant/revive/promote_skill、process/update/demote_memory、rewrite_doctrine)+ **immutable-core 对象级写保护**(DoctrineEntry.`__setattr__` 守卫,终审追全路径无洞)+ 技能生命周期(dormant 轮回复活,非法转移抛错)+ **编辑审计 Δ 轨迹**(EditLog,被拒编辑不入账,record 带 payload)+ **P0 多 regime 修复**(for_regime 成员匹配,真实种子 11 条多相位记忆已可查)+ patch/update 原子性。82 测试绿,subagent-driven 两段评审+终审 READY。
- **Phase-0b-3 已完成并入 main**(`youzi/harness/{snapshot,manager}.py` + 序列化):Harness 持久化——`HarnessState`/`EditLog` 序列化往返(byte-identical,真实种子验证)+ meta-tool before-image payload(JSON-safe via `_jsonable`)+ immutable 跨往返保真(`model_validate` 重建,守卫还原后仍生效)+ `Skill.applies_all`(相位通配,by_phase 认)+ `SnapshotStore`(版本化 JSON,原子写 tmp+os.replace,corrupt-load 守卫)+ `HarnessManager`(checkpoint/rollback_to 重绑 tools)。修了两处 `log or EditLog()` falsy-empty 旧 bug 并加 `__bool__=True` 杀掉整类。99 测试绿,subagent-driven 两段评审+终审 READY。
- **Phase-1 就绪债务(终审标记,非阻塞)**:① rollback 后旧 `mgr.tools/harness` 引用静默操作废弃态(已 doc;Phase-1 可加 epoch/失效句柄);② 无自动 checkpoint(Refiner loop 需 checkpoint 策略,如每周期/编辑前);③ 全量快照成本(~68KB/次,频繁则需保留/delta);④ before-image payload 仅审计、非 delta-replay 完整(不记派生字段副作用);⑤ 无并发锁(多进程共享 store 会 clobber);⑥ MetaTools.h/log 未强封装(债务#3)、⑦ 3 条种子 token(债务#6,seeds/README)。
- **Phase-0c 计划已写**(`docs/superpowers/plans/2026-05-30-phase0c-candidate-universe.md`):**候选 universe / 个股快照层**——`StockSnapshot`(frozen PIT,status=涨停/炸板/跌停)+ `CandidateUniverse`(按 code 索引+by_status/by_min_boards/by_industry)+ `build_universe(source,day)`(三池合成,经 GuardedSource 受防火墙保护)+ `_RENAME` 保留个股字段(封单/换手/行业/流通市值)。**依赖驱动的排序**:选股策略/评测 oracle/Agent 都要按 code 挑标的,而 `MarketState` 只有聚合量+代表票名字——故先建个股 universe。`MarketState` 不变。
- **roadmap**:Phase-0c 候选 universe → **Phase-0d 评测脚手架+已实现未来 oracle**(选股质量验收尺,需 universe 才能按 code 评)→ Hmin/Hexpert 基线 → 龙虎榜/题材线特征 + 仓位/组合层 → **Phase-1 = G 子 Agent + act→Refiner 闭环**(meta-tool+持久化+回滚底座已就绪)。

### Phase-0a 已知债务(终审标记,Phase-0b 处理)
- **PITStore 尚未接入取数路径**:应作为 read-through/write-through 插进 `GuardedSource` 内层(guard 仍在外把关日期),实现"边跑边快照"PIT 累积;docstring 的"写一次不被未来修订覆盖"目前只是注释、无强制。
- **幸存者偏差/PIT 成分未解**:akshare 概念成分是当前成分;退市/ST/改名/当时可交易池未处理。**当前防火墙只防"日期 lookahead",不防 survivorship**——别误以为绿灯=survivorship-safe。
- **`raw_sentiment` 权重是硬编码先验**:K/M/p 落地后应从注册表取权重,否则与"四层全进化"矛盾。
- **history 是内存平表、按位置索引**:长回放/重启不持久,且若 step() 跨索引未 observe() 会错位(非未来泄漏)。建议改 `dict[int,float]`/按日期键 + 持久化(PITStore 是自然落点)。
- **akshare 列名回归锚**:先跑一次 `scripts/smoke_akshare.py <真实交易日>`,把实际 `cols=[...]` 记进本文件 §4 作回归基线(若 akshare 改列名,特征会优雅退化为空默认而非崩溃/泄漏)。
- `as_of` 目前固定 15:00 收盘戳;日内 fill-feasibility/分时出货检测需 sub-day 粒度(schema 已是 datetime,前向兼容)。
