# 蓝图考古笔记(《自进化游资系统-架构蓝图-v1.0.md》,579 行,11 节)

## ① H=(p,G,K,M) 各构件设计意图 + 主映射表(§3, §6)

**总设计意图**:环境是"非平稳 + 对抗 + 反身"的 A 股超短市场;可持续的不是某个打法,而是**会自己改打法的系统**。H 是包住基础模型的可自编辑外壳,四构件全部经 meta-tool API 被就地 CRUD(Agent 与 Refiner 共享同一套 API,只是触发角色不同)。

| 构件 | 论文对应 | 设计意图 | 关键机制 |
|---|---|---|---|
| **p** doctrine | system prompt | 当前 regime 作战指导 + 禁忌口诀,随 regime 切换被 `rewrite_doctrine` 重写;周期性"增长↔简化" | **不可侵犯核**[修P3]:纪律/止损/风控红线 Refiner 永远改不动(防灾难性遗忘) |
| **G** 子 Agent 群 | battle/puzzle/self-reflection agents | 8 个具名子 Agent(见④),经 `define_subagent` 创建/编辑/删除 | `G_cycle` 只读 s_t、绝不写回定义自己输入(SSOT 铁律) |
| **K** 技能库 | 寻路技能 | 葵花宝典网格 + 模式/特征/失败检测三类参数化技能,**朝 oracle 自改进**(对应论文 Fig8) | `oracle_gap`[修P11] = 独立于 P&L 的技能-oracle 缺口度量;4 态生命周期 active/incubating/retired/**dormant**(retire≠delete,regime 回归自动 revive 候选) |
| **M** 记忆 | memory/notepad | regime×模式×结果 索引的教训 + 具名历史类比 + 失败签名库 | **放弃单调累积**[修P9]:regime 时戳 + 时间/regime 双衰减 importance;旧条目降权不删,留待"轮回"复活 |

主映射表其余要点:观测 o_t = MarketState(**相位/情绪在 s_t 侧,不在 H 内**);动作 a_t = DecisionPackage(人确认下单);oracle = **已实现的未来**(↔Dijkstra,交易优势但**会漂移**);episode = 一个完整周期轮回(冰点→主升→退潮→冰点),reset-free;capability floor = 数据/特征/模型/regime 样本量地板。

## ② 双环机制(§5, §6.5, §6.6, §7)

**Inner loop(每日收盘复盘,in-context 自精炼)**:
- 触发:F=1 交易日收盘 + 事件触发(相位切换大复盘);W=上线预热期只观测不编辑。
- Refiner 读 τ_{t-F:t} → 识别**交易失败签名**(追高被套/该走不走/卡位失败/退潮接力/预期差 read 反/踩防坑结构…)→ **四遍各一遍 CRUD**(Δp→ΔG→ΔK→ΔM)→ H_{t+1}=H_t⊕Δ,次日生效,不 reset。
- **最重要修正**[修P18]:同 episode 同 regime 信息累积**局部单调**有效,跨 regime 按 decay 加权 + dormant 复活通道——修正论文的"单调累积"(那依赖 Pokémon 平稳)。
- 蓝图给了 worked example(神马电力 6/28 退潮拐点 → 四遍编辑各改什么)。

**Outer loop(跨周期协同学习 — 现库尚未实现)**:
- 回放 emulator 上 π_θ 跑 K≈256 步 rollout(迭代 k 末游标/持仓态=k+1 起点,reset-free)→ PRM R(s,a,τ)∈[0,1] 滑窗打过程奖励(regime read/纪律遵守/预期差兑现/风险调整 P&L)→ 低奖励窗口 **teacher relabel**(oracle 给客观结果标签,frontier teacher 只做归因成"决策包+理由",**二者职责分离**[修P17]防循环验证)→ soft-SFT/LoRA(~3ep, ~5e-6)更新 θ → 影子盘 A/B + OOS 门,不达标回滚 θ_k[修P16]。
- PRM 铁律:t 时刻只用 ≤t 信息;relabel 产物只进训练集,永不进推理路径。
- θ 跨迭代更新 ⟂ H 回合内更新,co-adapt;人类 confirm/reject/modify = 免费 DAgger 专家标注[修P6]。
- 方案裁决:A(双环直译)=目标态;B(Harness-only 冻结模型)=MVP/Phase-1(当前代码即此);C(锦标赛)被吸收为 K/G 的**孵化育种场**。

## ③ 六道闸/对抗硬化中的"结构性防御"(§8, §6 各处)

靠**架构形状**(数据流/schema/隔离)而非靠纪律的:
- **PIT + as-of-date 防火墙**(闸⑥,P0 头号):实盘推理路径 L0–L4 只见 ≤t 信息;oracle 只存在于 outer-loop relabel 环节,产物只进训练集——**未来信息与推理路径在管线上物理隔离**。
- **SSOT 分离**(P0-②):相位/情绪属 s_t 客观观测、不属 H;禁止 harness 定义自己的观测——切断"Refiner 重写含相位的 p → p 又喂 G 判相位"的 confirmation-bias 闭环,靠数据归属而非提醒。
- **孵化锦标赛沙盒**:新建/复活技能结构上先入 incubating 态,OOS 显著胜出才 promote——不合格技能**够不到**现役位。
- **风控守卫层级**(L4 凌驾 L2 建议):G_risk 否决权、公告/监管 hard-constraint 否决器**优先级高于一切模式信号**——防御在分层拓扑里,不在提示词里。
- **不可侵犯核**:immutable doctrine 由结构保证 Refiner 改不动(代码里已落成 `__setattr__` 守卫双拦截)。
- **frozen-doctrine 影子对照 + 能力地板熔断**(闸⑤):常驻冻结基线,自进化跑不赢即**自动**回退/冻结 outer loop——回退是机制不是人为决定。
- **涌现技能审计闸**[修P15]:每个 create/promote 强制过闸,检查是否隐式依赖 as_of 之后信息、是否仅在模拟成本下成立。

偏"纪律/流程"的(对照):OOS/walk-forward 协议、purged CV、多 seed、影子盘爬坡门槛、模拟 vs 实盘成本 diff 警报、停训准则——这些靠评测流程执行,不靠代码形状。

## ④ G 子 Agent 群的目标形态(§3 映射表, §6.2, §6.4, §6.7)

蓝图规定 **8 个具名子 Agent**(现库只有主 Agent,ΔG-pass 是 no-op):
1. **G_cycle 周期/情绪分类器**(§6.2 详设最全):7 相位状态机 × per-题材线向量 + 全局母状态,判据可被 `patch_subagent` 编辑,是高频精炼热点,输出驱动葵花宝典选可用模式集;
2. 龙头/接力识别器;3. 题材挖掘器;4. 预期差评估器;5. **G_risk 风控/止损器**(§6.7:形态/regime/时间纪律三类触发 + 对买入建议的**否决权**);6. 复盘自省器;7. 公告/监管否决器(硬闸);8. fill-feasibility 评估器。
- **master_龙头_agent 分派结构**[修P12]:主控 Agent 把 per-decision 逻辑分派给具名 sub-check(弱转强/卡位/补涨/退潮接力否决/预期差档位);弱转强、退潮接力否决、预期差被指定为高频精炼热点。
- ΔG 的进化语义:对重复多步读盘模式 `create` 子 Agent;对检测到失败的识别器 `edit`;对从没 productively 调用的 `delete`。另有独立 **alpha-decay 监控子 Agent**(闸③)盯现役 K/G 的 OOS 绩效斜率。

## ⑤ 编排/会话/可观测性/UI 设想(可能被 DeepSeek Harness 框架替代的部分)

蓝图对这些**着墨最少、最"自造轮子"**——正是外部 agent 框架可接管处:
- **编排器 Orchestrator**(L2, §6.4):= 论文 orchestrator,"感知→K 并行匹配→排序→决策包"串联 + master 分派;蓝图只给日内时序表(盘前/竞价/盘中/尾盘/收盘五节点、事件触发节奏),无会话/进程模型设计。
- **HITL 人机界面**:唯一 UI 设想 = DecisionPackage schema 本身("人机界面"),含 human_confirm 字段(confirm/reject/modify+理由);交互性要求仅一句"决策包默认按置信度折叠,一屏可决"。确认回流 = DAgger 数据。
- **可观测性**:分散为若干机制而非统一设计——meta-tool 编辑审计留痕(合规要求"全程审计留痕")、evidence_ptr 指向 trajectory(`traj://...`)、θ 全程版本化 + 影子 A/B + 回滚、在线监控(决策质量衰减预警、与回放分布的 KL 漂移)、§6.9 指标板(7 类主指标 + 消融协议)。
- **没有的东西**:无 web 框架/服务化/session 管理/多用户/dashboard/日志基建的任何设计;`scratchpad` meta-tool(竞价真值表推演)是唯一"工作区"概念。蓝图自称"纯架构蓝图,不含代码"——编排循环、轨迹存储、审计日志、HITL 界面、监控告警全部是实现自由度,即可被现成 Harness/Agent 框架(会话持久化、tool-call 审计、trace 可视化、人审 UI)替代的空间;而 ①–④ 的领域机制(六道闸、四遍 CRUD、oracle_gap、dormant 轮回)是蓝图的不可替代核心。