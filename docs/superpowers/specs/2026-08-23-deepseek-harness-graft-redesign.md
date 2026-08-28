# DeepSeek Harness 嫁接重设计(合成稿)

> 日期:2026-08-23。产出方式:13-agent workflow——6 路 dsh 文档/仓库/Cordis 论文深读 + 2 路本项目权威文档重读 → 3 个独立立场设计(A 宿主壳 / B 插件原生 / C 会话中心)→ 2 个对抗评审(不变量守卫 / 工程忠实度)→ 本合成。
> 全部原始材料存档于 `docs/findings/2026-08-23-dsh-graft/`(研究笔记 ×8、设计 ×3、评审 ×2)。
> 本文写作纪律(承 C 案):每条 youzi↔dsh 映射标注**真同构 / 半同构 / 纯修辞**;每条未经一手验证的 dsh 能力标 **[假设待验证]**。

---

## 0. 一句话结论

**"以 dsh 为基底"应读作:dsh 作运行时基底(壳/会话/审批/调度),youzi 作领域基底(真相/尺/防火墙)——而不是把领域核心迁进 dsh。** 全盘插件原生化(立场 B)被两位对抗评审一致否决:dsh 现为 developer preview(repo 建立 2026-08-13,`0.0.0.dev0`,`SESSION_FORMAT_VERSION=0` 明言无兼容承诺,官方明示随时 breaking)——把"会被自进化编辑的活体 H"押在这样的地基上,是把研究皇冠交给一个 10 天大的框架托管。合成方案 = **A 的运营壳为底盘 + C 的研究环机件(修正后、条件化)+ B 只拆纯 Python 零件**。这次嫁接买到的是**壳与审计面**(UI/留痕/审批/调度),不是 alpha;北极星实验(HCH vs Hexpert)与嫁接完全解耦、永不被阻塞。

---

## 1. dsh 设计理念深理解(嫁接的认识论基础)

### 1.1 双支柱:"Everything is a plugin. Every run is traceable."

- **空间支柱(一切皆插件)**:models/tools/skills/sessions/sandbox/storage/scheduling/UI、乃至 agent loop 本身,全是 Cordis 插件;内核只管 "plugin mounting, unmounting, and dependencies"。扩展点在**配置层**(cordis.yml + bundle/profile/patch 叠层)不在源码层。没有特权 core——"Plugins, not loop changes"。
- **时间支柱(一切可溯)**:"**Model-visible means logged**"是**运行时断言**而非约定——凡进模型请求的必须可从 append-only SessionEvent 日志重建;LLM 消息历史是从日志**派生**的(`deriveMessages()`),从不单独存;resume/fork/replay 全部操作同一事件流。

### 1.2 Cordis 论文的理论内核(《A Programming Paradigm for Spatiotemporal Composability》)

- **Temporal**:效应建模为"作用于上下文并同时返回自己的逆"(`Γ → Γ × (Γ→Γ)`);卸载组件 = 应用累积的逆(LIFO)。"a component's teardown is **derived from its loading** rather than written alongside it"。
- **Spatial**:依赖注入形式化为 reactive coeffects——组件声明依赖,依赖齐备才激活、提供者消失自动回退重连;"a plugin whose dependency is unavailable stays inactive until it appears, without erroring"。
- **对本项目的镜像**:论文 §1.2.2 直指自进化 harness——没有 temporal composability,每次自我修改都要整体重启;"a faulty self-modification can disable the very process needed to recover"。这正是我们 `HarnessManager.rollback_to` + `_rebind` 手工债务的形式化解法(我们是快照式回滚,Cordis 是构造式回滚)。**核心哲学句**:"correctness that would otherwise rest on developer discipline becomes a **structural property of the paradigm**"——与本项目"不变量靠评审守"形成鲜明对照,也是本次嫁接最值得**借理念**(未必借运行时)的一句。

### 1.3 与 youzi 的深层同构(为什么嫁接在概念上诱人)

| youzi 既有机制 | dsh 对应物 | 同构度 |
|---|---|---|
| EditLog append-only 审计 | SessionEvent 日志 seq 连续、深冻结 | 真同构(痕迹层) |
| `checkpoint/rollback_to` + rebind | `fork(source, boundary)`,boundary 须"turn 间稳定位置" | 真同构 |
| 观测 vs 编辑边界(stats 直写不入 EditLog) | surface(进模型)/ log-only(仅留档)事件二分 | 真同构 |
| "live H 渲染进 system prompt" | `request/header` EpochHeader 全量请求快照 | 真同构(审计对偶) |
| compare 四臂 factory 注入防污染 | isolation realms("同 key 不同子树不同绑定") | 半同构(realm 是进程内语义,跨进程用不上) |
| `DecisionPolicy` 协议 + 实现注入 | Service Definition / Provider / Consumer 三角色 | 真同构(风格) |
| K 技能库(4 态生命周期 + SkillStats 信用) | dsh skills(SKILL.md 静态指令文件) | **纯修辞**——dsh skill 无生命周期/无战绩/无信用回注 |
| Hmin 裸基线 | Minimal 运行时模式(two-tool 消融基线) | 半同构(思想同) |

### 1.4 preview 现实(嫁接的物理约束)

- **Python 官方路径今天只有客户端**:`deepseek-harness-sdk`(pip,自带打包 runtime 二进制,无需系统 Node)以子进程 stdio JSON-RPC 驱动 dsh 会话;**Python 侧没有文档化的插件/工具注册 API**——想成为一等插件得写 TS。反向通道 `next_request/respond` 存在但零文档背书。
- **SDK 示例默认 `danger-full-access` + 继承全环境**——与防火墙/离线优先相抵,一切组合必须显式收紧。
- `domain/changed` 等事件总线是 Node 进程内语义,跨语言只能走持久层;SQLite 后端"拒绝旧 schema 无迁移"。
- macOS 14+ arm64 / Linux 支持,不支持 Windows;SDK config 未见 temperature 字段(研究臂 temp=0 是开放问题,解法见 §4.3)。

---

## 2. 合成设计总纲

### 2.1 三条不可谈判红线(任何波次、任何演进不得触碰)

1. **R1 工具面红线**:任何 dsh 会话(cockpit/act/refine)**永不配 bash/fs 类通用工具**。教训来自 C 案波次 2 的 bash 桥被评审击穿:PIT parquet 就在文件系统上,bash 即绕过 AsOfGuard 的前视侧信道,且可 sqlite3 直写绕过拒绝管线、可改 seeds——①②③一次全穿。跨语言调用只走**窄类型化工具**(TS `defineTool` 薄代理,白名单命令)。
2. **R2 真相红线**:H 与任何领域真相(store/EditLog/PIT)**永不进 dsh 持久层**,直到 `SESSION_FORMAT_VERSION≥1` 且有升级路径。裁决规则原句:**store 是唯一真相,dsh session log 是观测投影;禁止任何代码从 session log 读数据回流领域。**
3. **R3 北极星红线**:北极星实验(真实多窗 HCH vs Hexpert)永远可在纯 Python 路径独立跑;**任何嫁接波次不得成为其前置**。

另一条评审强制修正(A 案唯一真洞):**钱路径不进模型工具面**——`confirm_decision`/`record_fill` 绝不做成 cockpit LLM 可调用的"工具+approval ask"(载荷是 LLM 可伪造的普通 JSON;ops_repo 现状也无 human-confirm 证明参数)。写路径走 `ctx.commands` 人类命令通道("dispatches without a model turn",出处 repo architecture.md;**API 细节 [假设待验证]**),验证不过则保留 B-web FastAPI 录入页。**youzi_web 冻结保留,不删除**(为 v0 preview 壳杀掉已工作的备胎过于激进)。

### 2.2 双轨架构

```
┌─ 运营轨(A 底盘)──────────────────────────────────────────────┐
│ dsh web(:3080)profile: youzi-cockpit                          │
│   cockpit agent = 操作员助手,非决策者;工具面 = 桥只读白名单     │
│   审批/留痕/调度 = dsh interaction/sessions/schedule            │
│   写路径(确认/成交)= ctx.commands 人类通道 或 B-web 录入页      │
│      │ 每次调用 spawn 短命 python -m youzi_bridge.cli           │
│      ▼ 信封 v1(youzi 定义契约,golden fixtures 双侧共享)        │
│ youzi_bridge/(新包,地位同 youzi_web:单向依赖领域)             │
├─ 领域核心(一行不动)───────────────────────────────────────────┤
│ youzi/:GuardedSource→universe/features→LLMAgentPolicy→eval    │
│   →credit→Refiner(meta-tool→EditLog)→InnerLoop/compare        │
│ store/SQLite=唯一真相 · PIT parquet · harness snapshot          │
├─ 研究轨(C 机件,条件化)────────────────────────────────────────┤
│ SessionRunner 窄协议(run(prompt,session_id)→SessionResult)     │
│   实现①:现行 LLMClient 直连(默认,北极星走这里)               │
│   实现②:dsh 会话(HarnessSessionPolicy 新臂,同窗对跑先证不劣)  │
│ E1 录放代理(OpenAI 兼容 MITM,base_url 指入;兼改写 temperature)│
└────────────────────────────────────────────────────────────────┘
```

- **运营轨**(嫁接第一收益点):dsh 接管 youzi_web 正在自造/将要自造的壳——驾驶舱 UI、人机会话 append-only 留痕、审批闸、调度。TS 桥 <300 行零业务逻辑,信封 v1 由 Python 侧定义,dsh breaking 时受灾面钉死在桥内。
- **研究轨**(条件化,不急):act 外包给 dsh 会话**只作为新增一臂**进 compare 与 `LLMAgentPolicy` 同窗同尺对跑,先证不劣再谈切换;refine 会话与 EditGate(fork+影子验收)是 dsh 格式稳定后的第二阶段选项。CI 永不 spawn dsh 二进制(FakeSessionRunner 兜底)。

### 2.3 组件映射表(合成后)

| youzi 构件 | 处置 | 去向/理由 |
|---|---|---|
| `data/ replay/ universe/ features/ schemas/ eval/ agent/ refine/ harness/ loop/` | **原封保留** | 领域独有,任何框架给不了;防火墙/尺/拒绝管线是研究本体 |
| `youzi/store/`(SQLite 7 表)+ EditLog + PIT | **保留,唯一真相**(R2) | dsh storage domain 明确不用 |
| `llm/client.py + cache.py` | **保留**;新增录放代理(§4.3) | 决策/精炼 LLM 调用留 Python |
| `youzi_web/` | **冻结保留**(录入页可能长期在此) | dsh UI 扩展文档缺失;preview 壳不配当唯一 UI |
| `loop/run_store.py` | 按既定 C 期退役进 SQLite research 表 | 与嫁接正交,不搬进 dsh session log |
| — 新增 `youzi_bridge/`(Python CLI)+ `dsh-youzi-bridge`(TS,<300 行) | **新建** | 运营轨唯一嫁接面 |
| — 新增 `SessionRunner` 协议 + `FakeSessionRunner` | **新建**(研究轨预埋缝) | CI 零 Node;将来任何 act-经-dsh 实验必走此协议 |
| G 子 Agent 群(蓝图目标态) | 远期:dsh subagent 树(`subscribe_session_notifications` 子孙归并) | dsh 格式稳定后 ΔG 脱离占位的最短路径;半同构 |

---

## 3. 六条硬不变量逐条论证(合成后)

1. **未来函数防火墙**:决策路径 100% 在 Python 进程内,结构防御一行不动。dsh 侧三道:(a) cockpit 工具面无 bash/fs(R1),模型够不到文件系统上的 PIT;(b) 桥工具 schema 不暴露日期参数,`decide` 内部钉 t=当日;(c) 含未来数据的研究回放默认不经 dsh;若研究臂接入,act 会话零工具 + runtime 不持有任何数据源(只收 prompt 文本)+ **日志 lint**(act 事件流断言无 oracle 标签类事件、`request/header` 快照与自渲染 H 逐字比对)——防火墙从"结构+评审"升级为"结构+评审+事后机器证明"。
2. **观测 vs 编辑边界**:零迁移。桥不暴露任何 meta-tool;`refine_daily` 是粗粒度触发命令,编辑仍在 Python 拒绝管线内完成入 EditLog。研究轨 refine 会话(远期)只经 TS 窄代理到达同一管线。
3. **immutable-core**:`__setattr__` 守卫 + 双拦截原样。第三层加固(C 案抢救,纯 Python 独立采用):**编辑重放/折叠时对 immutable 目标拒绝入账**——即使入口被绕过,重建 H 时红线编辑也不生效。
4. **领域核心纯净**:`youzi/` 零新依赖;`youzi_bridge/`/`youzi_dsh/` 与 `youzi_web/` 同级单向依赖;架构测试断言 `youzi/*` 不 import 桥/SDK。dsh 隔在两层进程边界外,可整体拔除。
5. **离线优先**:youzi CI 仍纯 Python 全离线;信封合同测试直调 `youzi_bridge.cli`(FakeSource/MockLLM/临时 DB);TS 桥测试独立 lane,**dsh runtime 永不进 youzi CI**;研究轨用 FakeSessionRunner。诚实盲区:「dsh web+桥+审批」端到端只能手动/独立 lane——同"MockLLM 测不了 refine 实效"性质,且只覆盖壳。
6. **人确认下单**:三层独立——(一)全系统无券商接口,下单物理不可能(唯一真结构防线,嫁接不触碰);(二)钱路径不进模型工具面(§2.1 修正:ctx.commands 或 B-web);(三)dsh approval ask 作附加层(**粒度 [假设待验证]**,降级不破前两层)。

---

## 4. 立即可做的抢救零件(与 dsh 成败无关,评审一致点名)

### 4.1 纯 Python 结构升级(并入既定 D 期 store 迁移)
- **`skill_def` / `skill_stats` 表级物理分离**:把 `_PATCH_FORBIDDEN` 从字段黑名单升级为 schema 结构——patch 物理写不到观测字段(B 案抢救)。
- **`UNIQUE(trajectory_id)` 幂等账本**:闭合 `apply_credit` 重复累加已知债务;信用事件带完整后像(whole-value 规则,抄 dsh projection)。
- **fold 式 immutable 重校验**(§3.3 第三层)。

### 4.2 方法论采纳
- **"真同构/半同构/纯修辞"三级标注**定为设计文档写作规范(本文即用)。
- **keyless 断言测试**:任何暴露工具面的组合,启动断言 `schemas()` 恰为白名单集合。
- **同窗对跑先证不劣**:任何 dsh 路径的决策臂,准入门=与现行实现同窗同尺对比不劣。
- **`--dump-config` 产物入库比对**:profile 正确性从口头纪律变成可 diff 工件。

### 4.3 E1 录放代理(白赚的基建)
自建 OpenAI 兼容 MITM 代理(Python):经 `DEEPSEEK_BASE_URL`/`base_url` 指入,record/replay 决策与精炼请求;顺手在转发时**改写 temperature=0.0**(解 SDK 无温度字段问题),改写行为入日志以免污染 request/header 审计比对。无论嫁接成败都是 E1 缓存的升级形态。

---

## 5. 迁移波次(合成)

| 波次 | 内容 | 门/回退 |
|---|---|---|
| **W-P(即刻,纯 Python)** | §4.1 三件套并入 D 期 spec;录放代理 | 与 dsh 零关;正常 spec/plan 流程 |
| **W0 侦察 spike(1–2 天,可整体丢弃)** | 合并三案 [假设待验证] 为一张清单逐项实测(见 §6);产出=答案清单,不触 youzi 仓库 | **总门:后续一切波次以实测答案为准**;回退=删目录零痕迹 |
| **W1 只读驾驶舱** | `youzi_bridge/` 只读命令 + TS 桥 + youzi-cockpit profile;youzi_web 并行不动 | 信封合同测试进 CI(纯 Python);回退=不开 dsh |
| **W2 写路径** | 确认/成交录入:优先 ctx.commands 人类通道(W0 验证);不可用则**留在 B-web 录入页**,dsh 只读呈现 | 回退=B-web(spec 尚在);youzi_web 冻结不删除 |
| **W3 调度+复盘会话化** | 盘前/盘后 dsh schedule(证伪退 cron);每日复盘 dsh session 留痕;EditLog 只读投影进会话 | 逻辑本体全是幂等 CLI(纯 Python 可测) |
| **W-R 研究轨(条件化,独立决策)** | ①SessionRunner+HarnessSessionPolicy 新臂同窗对跑 → ②refine 会话 TS 窄工具桥(R1:无 bash) → ③EditGate=fork+影子验收 | 前置:北极星已在纯 Python 路径先跑;dsh 格式趋稳;**EditGate 须先修自证偏差**(评估窗与塑造该编辑的证据期不相交,否则闸是虚设——评审裁定) |

被否决不做的:H 真相迁 dsh storage、拒绝管线 TS 移植、H-as-fold 全套重构搭嫁接便车(若做,按独立阶段走 spec/plan)、Code Mode、"H 即 bundle-patch" 深嫁接。

---

## 6. W0 侦察清单([假设待验证] 合并)

1. approval ask 对自定义工具的粒度与 UI 形态(A 案第二防线成色所系)
2. `ctx.commands` 人类命令通道 API(钱路径修正案所系)
3. schedule/jobs API(证伪退 cron,损失仅"调度进同一 UI")
4. `dsh plugin --profile X add ./本地目录` 装载 + `--dump-config`
5. 零工具 act 组合可行性(minimal 例最少带 bash+editor;fallback:只读空 workspace——但按 R1 需确认无 fs 触达)
6. per-臂 temperature 控制(录放代理改写为兜底解)
7. `llm-replay` adapter 语义;session JSONL 落盘确切路径;中文 UI 程度
8. TS 桥 spawn 子进程是否受 sandbox-policy 管辖(设计不依赖它,防线在工具面)

---

## 7. 风险与开放问题

1. **preview 漂移是首要风险**:对策已内建(真相不进壳、信封由我方定义、TS 桥唯一受灾面、每波可回退、版本钉 commit)。残余:dsh 大改时驾驶舱短暂退回 youzi_web/CLI。
2. **cockpit 言论逃逸审计面**(评审 J1):操作员据以行动的可能是 cockpit 的二次转述(在 dsh log 里)而非 DecisionPackage 原文。对策:工具结果渲染只呈现 DecisionPackage 原文 + decision_id 溯源;system prompt 钉"呈现与操作,不改写建议"——诚实承认这层是纪律不是结构。
3. **spawn-per-call 对长任务**:`decide`/`refine_daily` 内含真实 LLM 调用(30s–数分钟),timeoutMs 语义与中断时 Python 侧事务原子性需在 W1 实测(refine 已有"当日跳过、H 不变"的失败语义兜底)。
4. **杠杆的诚实定价**:本嫁接买到的是壳与审计面;若北极星证明自进化无 alpha,运营 Co-pilot 的 UI/审批/留痕仍然成立——这恰是嫁接把宝押在"无论研究成败都需要的部分"上的理由。
5. **哲学收获与远期期权**:Cordis 的构造式回滚/反应式重连是 `_rebind` 债务的理论解;Python descriptor 协议被论文点名可行——若 dsh 开放 Python 插件口或格式到 v1,C 案(会话中心)是升级路线图,B 案封存为远期蓝图。
