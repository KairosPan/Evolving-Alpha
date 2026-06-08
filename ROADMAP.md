# ROADMAP — 自进化游资系统(youzi)

> 总图:我们在造什么、走到哪、下一步去哪。详细交接见 `PROJECT_STATE.md`;实验记录见 `docs/findings/`;每阶段 spec/plan 见 `docs/superpowers/`。
> 截至 2026-06-08 · `main` · **294 测试全绿(离线)**。

---

## 北极星

把论文《Continual Harness》的 `H=(p,G,K,M)` 两环自进化机制,落到 A 股**游资/超短**交易(《轮回.docx》playbook),做一个**决策支持 Co-pilot**(系统排候选 + 计划 + 理由,**人确认下单,绝不自动交易**)。

**中心问题(尚未回答):自进化(每日精炼 H)能否产生 alpha —— 即 `HCH`(自精炼)跑赢 `Hexpert`(冻结种子)?**

当前诚实答案:**还不能,但已从"有害"修成"无害"**。
- 改进前:自精炼 3/3 窗退化于 frozen(Δ −0.02~−0.22)。
- 1b-3d 退役纪律后,temp=0 多窗池化:**HCH +0.222 ≈ Hexpert +0.219(打平)** > 裸追高 +0.185 > 空仓 0。
- 即:**1b-3d 把自进化从"有害"修成"无害(与 frozen 持平)";让它"有益(超 frozen)"是下一个、也是更难的前沿。**(findings §8/§9)

---

## 不可动摇的边界(贯穿所有阶段)

1. **决策支持,非自动交易** —— 系统给候选/计划/理由,人确认。
2. **未来函数防火墙** —— 决策只用 ≤t 信息(GuardedSource/AsOfGuard);打分在 t+horizon;已实现未来只作事后 oracle 标签,绝不回灌 ≤t 推理。
3. **观测 vs 编辑边界** —— SkillStats 由 `apply_credit` 直接写(观测);结构性编辑走 9 个 MetaTool 入 EditLog。
4. **领域/web 分层** —— `youzi/`(领域)零依赖 web;`youzi_web/`(web)单向依赖领域。
5. **离线优先** —— 全部逻辑离线可测(FakeSource/MockLLM/TestClient);live(akshare/DeepSeek)是末端可换适配器。

---

## 已完成(并入 main)

### 地基(Phase-0)
- **0a–0d**:数据回放 + 未来函数防火墙 + universe + 评测尺 + 种子 H(57 技能/21 记忆/doctrine,从《轮回》抽取)。

### 自进化内环(Phase-1a–1c)
- **1a** Agent:读市场态 + universe → 排候选 + 计划 + 理由(act)。
- **1b-1** 观测层:Trajectory / 信用分配(apply_credit)/ 失败签名。
- **1b-2** LLM Refiner:论文式 4-pass CRUD(Δp→ΔG→ΔK→ΔM)精炼 H。
- **1b-3a** 内环编排:`InnerLoop`(act→延迟打分→在线信用→能力地板熔断→每日 refine,reset-free)。
- **1b-3b** 度量对比:`compare_harnesses` 四路同窗同 oracle(HCH/Hexpert/Hmin)。
- **🔬 真实数据验**:发现自进化退化于 frozen(论文 §6.9 复现,病因=Refiner 小样本过度退役)。
- **1b-3d** Refiner 纪律化:退役证据门(n≥K)+ faded≠nuked 提示纪律 → **治住退化根因**(复测打平)。
- **1b-3e-1/2** 收益 oracle + 打分接入:可插拔 `Scorer`(`PoolScorer` 池成员制 / `ReturnScorer` 前向收益);`apply_credit` 用 `sc.score` → 收益作 expectancy(更细信号)。
- **1c-PIT** 数据快照 + 离线打分:`PITStore`/`SnapshotSource`/`capture_window` —— 一次性建库,之后离线无限次跑(治 akshare 限流;findings §10/§11)。

### 前端平台(FE,2026-06-08 起 · FastAPI+HTMX 纯 Python · 模块化"加功能=加 features/<name>/")
- **FE-0** web 地基:外壳 C(图标轨+子导航)+ 功能模块注册表 + `data_access` + 首模块 **research/H 查看器**。
- **FE-B** 研究驾驶舱全量:`run_store`(持久化 ComparisonReport)+ 3 视图(**三方对比 / refine 时间线 / trajectory**,一份产物驱动)+ 运行选择器。
- 看成品:`python scripts/sample_run.py` → `python scripts/serve_web.py` → http://127.0.0.1:8000

---

## 进行中 / 卡住

- **🚧 真实收益对比(量化主线的关键一跳)**:`smoke_compare --scorer return` 离线跑,看更细的收益信号能否让 HCH 产 alpha。
  **当前卡在 akshare OHLCV 端点硬拒连**(探针 0/5,findings §11)—— 纯外部阻塞、非代码问题。地基(PIT capture/离线打分)全齐,**待 akshare 恢复(off-peak)建库一次即可跑**:
  `python scripts/capture_window.py <s> <e> snap`(幂等可续跑)→ `YOUZI_RUNS_DIR=runs YOUZI_SNAPSHOT=snap python scripts/smoke_compare.py <s> <e> 2 0.0 return`。

---

## 路线图(按轨道)

### A. 量化研究主线 —— 让自进化"有益"(产 alpha)
> 北极星就在这条线上。当前"无害",目标"有益"。

1. **真实收益对比**(↑卡 akshare;恢复即跑)—— 第一手证据。
2. **更强的训练信号**:更长 horizon / N 日收益 oracle、更细的失败签名、regime 分层评测 —— 让 Refiner 学到真东西(短窗/horizon=1 下编辑常不改决策,边际作用小)。
3. **1b-3c 影子 Hexpert 严格地板**:环内并行跑冻结 agent,HCH 滚动跌破 margin → 熔断(论文式实时保护;现用自相对地板)。
4. **1c 协同学习外环**:replay + PRM + oracle relabel + LoRA(需 GPU)—— 把内环精炼沉淀成参数。
5. **增强**:龙虎榜/题材线、仓位/组合层、按 regime 选择性提示注入(现全量 ~24KB/次)。

### B. 数据 / 基础设施
1. **OHLCV 多源 fallback**(eastmoney→sina→tencent)—— 抗单端点故障(纯离线小切片,当下就能做)。
2. **真历史回测**:自建 PIT 数据(边跑边快照),解锁长窗 + 治幸存者偏差(akshare 池仅最近 ~30 交易日)。
3. **熔断 scorer-aware 重标定**:ReturnScorer 下 score=收益 ~±0.1/日,floor_abs=-0.2 几乎不触发。
4. **LLM 响应缓存**:让真实跑也能确定性 replay(现只治了 akshare,DeepSeek 仍 live)。
5. fill-feasibility(一字涨停次日买不进)、成本/滑点。

### C. 前端平台(成长型 · 加功能=加模块)
1. **FE-A 决策驾驶舱**(下一步):每日决策展示(市场态 + 排序候选 + 理由 + 计划 + 人工确认),对 `SnapshotSource`+(Mock/live)LLM 跑。
2. **从 UI 触发跑批**:网页里跑 compare/capture(需异步任务)。
3. **news 分类**模块:新闻 → 题材/情绪信号(各自一个 `features/news/`)。
4. **agents 编排**模块:可视化 InnerLoop/Refiner 编排(富交互画布可嵌 JS island)。
5. 研究侧深钻:trajectory 单步详情/逐技能信用/签名页、多 run 对比、run-store 清理/分页。

---

## 债务清单(登记,非阻塞)

| 债务 | 轨道 | 触发风险 |
|---|---|---|
| OHLCV 多源 fallback | B | 单端点(eastmoney)挂则全挂(已发生) |
| 真历史回测 / PIT 自建 / 幸存者偏差 | B | akshare 池仅 ~30 交易日 |
| 熔断 scorer-aware 重标定 | B | ReturnScorer 下熔断失效 |
| LLM 响应缓存 | B | 真实跑不可确定性 replay |
| 选择性提示注入(按 regime) | A | 现全量 ~24KB/次,贵 |
| friction:update_memory lesson_id / 重复 lesson_id | A | 浪费编辑额度(干净拒绝,不影响正确性) |
| fill-feasibility / 成本滑点 | B | 收益高估 |
| FE-A / 触发跑批 / news / agents | C | 平台广度 |

---

## 怎么读这张图

- **想知道"自进化行不行"** → 看北极星 + 轨道 A;一手证据在"真实收益对比"(卡 akshare)。
- **想现在能稳定推进、不依赖外部** → 轨道 B 的 OHLCV fallback、轨道 C 的 FE-A,都是纯离线小切片。
- **每个阶段都走** brainstorm → spec → plan → subagent 实现 + 两段评审 + opus 终审 → FF 合并 → 推送。spec/plan 在 `docs/superpowers/`。
