# 嫁接设计:youzi × DeepSeek Harness(立场 B:深度分解·插件原生)

> 引用图例(每条 dsh 能力可在研究笔记指认):【P】=dsh:philosophy 【G】=dsh:guide 【S】=dsh:python-sdk 【D】=dsh:develop 【R】=dsh:reference 【M】=dsh:repo。笔记未覆盖处一律标 **[假设待验证]**。

## 设计总览(一段话立场)

认真对待 "Everything is a plugin"【M:repo description】:把 youzi 拆成两个纯核 + 一层 dsh 插件接线。**TS 侧**承载"会被自进化编辑的活体"——H=(p,G,K,M) 迁入 dsh storage domain(我们声明 schema 的分域表【R/storage】),9 个 meta-tool 变成 `ctx.tools.register` 的 dsh 工具【D/basic/tool】、拒绝管线移植为不依赖 cordis 的 `youzi-harness-kernel` 纯 TS 包(照抄 dsh 自家纪律"接线归 cordis.yml,逻辑归包"【M:examples/AGENTS.md】);act 与 refine 都变成 dsh agent session(不同 preset/profile),人确认走 approval/interaction【M:packages】+ tools/pre-execute 的 ask【R/tools】,会话/留痕/回放全部交给 append-only session log【R/session】。**Python 侧**只留 dsh 给不了的纯数值/数据层:GuardedSource/PIT 防火墙取数、universe/features、oracle/打分/可成交/统计裁决、credit 数值、B2 熔断判定、运营台账 SQLite——打包成 `youzid` 侧栏进程,与 dsh 经一条我们自有的双工 JSON-RPC 信道缝合(传输形态照抄官方 Python SDK 的行分隔 stdio JSON-RPC【S】,但协议两端全是我方代码,零未验证 dsh API 依赖)。诚实前置:这是把"领域核心一语言一包"改成"双语言双核",拒绝管线要移植、dsh skill 概念装不下 K 的生命周期、preview 版随时 breaking——这些代价在下文逐条标价,不藏。

## 组件映射表

| youzi 构件 | dsh 概念 | 处置 | 理由 / 出处 |
|---|---|---|---|
| `LLMAgentPolicy`(act) | 交易 preset 的 agent session(turn/step loop) | **替换** | 工具循环/留痕/派生历史 dsh 原生【M:architecture.md】;决策输出改为 `submit_decision` 工具,schema=DecisionPackage,参数在工具边界推断校验【D/basic/tool】 |
| `agent/parse` 幻觉过滤 | `submit_decision.execute` 校验 + `tools/post-execute` waterfall | **融合** | universe 内 code 过滤/confidence 钳制移入工具执行【R/tools】;turn 失败→空仓兜底留在编排侧 |
| 9 个 meta-tool | 9 个 dsh tools(仅 refine preset 挂载) | **替换**(TS 移植) | `ctx.tools.register(defineTool)`【D/basic/tool】;拒绝管线入 `youzi-harness-kernel`;闸门挂 pre-execute waterfall(allow/deny/ask)+ guard【R/tools】 |
| `EditLog` | storage domain `harness_edit` 表(真相)+ 自定义 SessionEvent(审计投影) | **融合** | domain 原子排队写【R/storage】;SessionEventMap 可由下游插件 merge 新类型【R/persistence-catalog】;既定 D 期"拆 harness_edit 表"被 storage domain 吸收 |
| `HarnessManager.checkpoint / rollback_to` + `SnapshotStore` | content-addressed 版本表 + roll-forward revert + `domain/changed` 反应式换绑 | **替换** | rollback=写指回旧内容的新版本行;消费方经服务解析 H,提供者变更→依赖 fiber 自动卸载重载【D/framework】——`_rebind` 手工债务被结构性解决(笔记明点此共振【P】) |
| K `SkillRegistry`(4 态生命周期) | `skill_def`/`skill_stats` 双表 + 动态 SkillProvider 投影 | **融合** | `ctx.skills.registerProvider()` 支持动态源【R/skills】,笔记称此为"最顺嫁接点"【D】;**诚实:dsh skill 是静态指令概念,无生命周期/stats/信用**——生命周期机器在我们的表里,skill 只是 active 子集的模型可见投影 |
| p `Doctrine`(含 immutable 核) | storage domain + system-prompt 段贡献插件 | **融合** | "插件贡献 system section"有快照测试文化背书("unintended system section fails the job"【S:development.md】);system-prompt 子系统页未读→贡献 API 细节 **[假设待验证]**;immutable 核=密封种子文件渲染时强制并入 |
| M `MemoryStore`(双衰减) | `lesson` 表 + 检索注入(context) | **融合** | 注入必落日志——"Model-visible means logged" 是运行时断言【M:architecture.md】,检索注入反而首次获得强制审计;衰减数值在 youzid 算、经命令通道写 |
| G 子 Agent 群(现为 no-op) | `dsh-tool-subagent` + `preset` 包(per-session 合成 agent) | **新生** | 隔离委托 + 子会话树事件自动归并【R/tool-catalog】【S】;`define_subagent` 写 preset 行→ΔG 首次可实现;运行时创建 preset 是否支持 **[假设待验证]** |
| `Refiner`(refine 半环) | refine preset 的独立 agent session,schedule 触发 | **替换**(编排) | Refiner 本就是"LLM+工具+拒绝";证据包由 youzid 组装、作 prompt 注入;`packages/schedule` + web-schedule 示例存在【M】,API 细节 **[假设待验证]** |
| `refine/credit.apply_credit` | Python 数值保留;写入走 bridge 非模型命令通道 | **融合** | `ctx.commands` "dispatches without a model turn"【M:architecture.md】语义对口;加 UNIQUE(trajectory_id) 幂等账本——顺手闭合"无幂等守卫"已知债务 |
| `InnerLoop` | 拆三份:日节律→schedule(运营)/Python 驱动(研究);打分/水位线/熔断数值→Python;refine 触发→schedule+bridge | **融合** | 熔断/水位线是评测数值,dsh 无对应物;回滚动作经 bridge 下发 revert(入 EditLog) |
| `compare_harnesses` | Python 保留主驱动;臂隔离=每臂独立 runtime 进程 + 独立 profile/session_root(isolate realm 备选) | **保留+增强** | factory 防污染 ↔ isolation realms 同构(笔记明点【P】);`isolate: {…}` 服务隔离【D/framework/service】 |
| `WalkForwardEval`/oracle/scorer/fill/stats | 无对应物 | **保留**(Python) | 纯数值领域尺,任何 harness 都给不了 |
| `data/`+`replay/`(GuardedSource/PIT) | 经 youzid 暴露为日锚定只读服务 | **保留**(Python) | 防火墙结构防线原样;dsh 侧数据工具**无日期参数** |
| `llm/client`+`CachedLLMClient` | LlmAdapter seam + llm-replay adapter | **替换**(act/refine 路径) | `registerAdapter`/`stream()`【R/llm-streaming】【D/practice/llm-adapter】;llm-replay 存在但细节未读 **[假设待验证]**;纯 Python 试验路径保留原件 |
| `loop/run_store` | session log(JSONL/SQLite 后端【G】【R/persistence】)+ 既定 C 期 research 表 | **退役** | transcript 归 dsh、数值产物归 Python research SQLite,与既定路线一致 |
| `youzi_web` 决策驾驶舱 | dsh Web UI + interaction/approval | **退役**(分步) | 权限询问/审批 UI 现成【G:quickstart】【M:packages/interaction】;**ops 录入页暂留 FastAPI**——dsh UI 扩展开发文档完全缺失【D 诚实清单】 |
| `youzi/store` 运营 7 表 | 不迁移;dsh 经工具读、写经 ask 审批 | **保留**(Python 真相) | 钱数据写者是"人+命令 API",非 agent;笔记警告 preview 期勿把真相迁入 dsh 持久层【M 启示3】 |
| seeds(pydantic 校验) | 入口权威不变;TS 侧 Schemastery 镜像 | **融合** | "Export schemas, not plain objects"、非法配置加载期报错【D/basic/config】;跨语言金样一致性测试压漂移 |

## 运行时架构

```
                ┌──────────────────────── dsh 运行时(Node/Cordis)────────────────────────┐
                │ profiles(bundle+patch 叠层【M】): trading.yml / refine.yml / arm-*.yml     │
 人(浏览器)◄──►│ Web UI + interaction(approval: ask)        schedule(盘前/收盘节律)       │
                │        │                                          │                        │
                │  agent loop(turn/step)◄─ system-prompt 段:p 渲染 + K(active)投影 + M 检索 │
                │        │ tool calls                                                        │
                │  ┌─────▼─────────────────────────────────────────────┐                     │
                │  │ ToolRuntime:pre-execute(allow/deny/ask)→ guards → │                     │
                │  │  execute → post-execute【R/tools】                 │                     │
                │  │  · 只读数据工具(无日期参数,as_of 钉在会话)        │                     │
                │  │  · submit_decision(schema=DecisionPackage)        │                     │
                │  │  · 9 meta-tools(仅 refine preset)· ops 写工具(ask)│                     │
                │  └─────┬───────────────────────┬───────────────────┘                     │
                │  youzi-bridge 插件      youzi-harness-kernel(纯 TS:拒绝管线/regime 归一)  │
                │        │                       │                                           │
                │        │        storage domains:doctrine/skill_def/skill_stats/lesson/     │
                │        │          harness_edit/version(+domain/changed 反应式通知【R】)    │
                │        │        session log:append-only,自定义 harness/* 审计事件【R】     │
                └────────┼───────────────────────────────────────────────────────────────────┘
                         │ 一条双工行分隔 JSON-RPC(我方自有协议;传输形态同官方 SDK【S】)
                ┌────────▼──────────── youzid(Python 侧栏进程)─────────────────┐
                │ data:AsOfGuard/GuardedSource → PIT parquet → universe/features │
                │ eval:oracle/scorer/fill/stats · credit 数值 · B2 熔断判定       │
                │ store:运营 7 表 SQLite(真相)· research 表(C 期)              │
                └─────────────────────────────────────────────────────────────────┘
 研究模式:Python compare_harnesses 为宿主,经 deepseek-harness-sdk 拉起 N 个隔离 runtime
 (每臂独立 profile + session_root),bridge 配置连回 Python 进程内的 youzid 服务;
  打分/水位线/熔断/bootstrap 裁决全在 Python,天平不动。
```

**数据流(运营日)**:schedule 建交易会话(as_of=今日钉入会话配置)→ system prompt 由 p/K/M 三个投影段合成(快照测试锁死每一段【S:development.md】)→ agent 调只读数据工具(bridge→youzid→GuardedSource,frozen 快照整对象返回)→ `submit_decision` 校验(code∈universe、confidence 钳制)后写候选/决策草案 → 人在 Web UI 经 approval 确认 → ops 写工具(ask 闸)落 Python 台账。**收盘**:schedule 触发 youzid 对 t−horizon 决策延迟打分 → credit 经 bridge 命令通道写 `skill_stats`(幂等账本,不产生编辑事件)→ B2 熔断数值判定,触发则下发 revert(写新版本行 + 入 harness_edit)→ refine 会话(refine preset)接收证据包,经 9 meta-tool 编辑 H → `domain/changed` 通知,次日会话投影出新 H——无人手 `_rebind`。

## dsh 买到了什么(逐条指认出处)

1. **append-only 会话日志 + resume/fork/replay 同一事件流**【P 官网原文】【R/session:fork(boundary)/flush/deriveMessages/崩溃合成 turn-end】——run_store 的 transcript 职能整体退役;`request/header` EpochHeader 全量快照【R】= "渲染后的 H 进 system prompt"的免费审计对偶,HCH vs Hexpert 任意历史决策可重建请求。
2. **工具管线闸门**:pre-execute waterfall(allow/deny/**ask**)→ monotonic guards → post-execute【R/tools】【R/capability-seams】——六道闸从"提示词+评审纪律"变成机器挂点;`schemas()` 白名单投影("must never leak into a model request"【D】)保证模型可见面显式。
3. **审批/人确认基建**:interaction 包(approval/permission/ask-user)【M:packages】+ Web UI "先问再执行"【G:quickstart】+ permission-presets(sandbox×approval)【G:config-catalog】。
4. **Fiber 生命周期/服务反应式装卸**:依赖消失→消费方自动卸载、回来自动重载【D/framework】——rollback 旧引用悬空债务的结构性解法(笔记明点共振【P】)。
5. **storage domains**:DomainSpec 声明 schema、原子排队写、`domain/changed`、sqlite/json 后端可换【R/storage】——H 的 D 期 SQLite 计划换壳落地。
6. **skills 动态 provider**:`registerProvider()` + 六级来源 rank【R/skills】——K 的 active 投影有官方接口。
7. **LlmAdapter seam + llm-replay**:实现 `stream()` 即换 provider【R/llm-streaming】;llm-replay 可替代 CachedLLMClient 录放(细节未读 **[假设待验证]**)。
8. **subagent 隔离委托 + 子会话树事件自动归并**【R/tool-catalog】【S:subscribe_session_notifications】——G 群与多臂审计的现成底座。
9. **profile/bundle/patch 叠层 + isolate**【M:architecture.md】【D/framework/service】——臂配置=一层 patch,防交叉污染有机制不靠约定。
10. **schedule/jobs**:包与示例存在【M:packages, examples/web-schedule】,API 细节 **[假设待验证]**。
11. **Python SDK 子进程驱动**:行分隔 JSON-RPC/通知订阅/事件全量留痕(RunResult.events)【S】——研究模式的驱动通道。
12. **快照测试文化**:任何插件多贡献一段 system prompt 即 fail【S:development.md】——p 投影的防污染验收现成范式。

## 六条硬不变量逐条论证

**① 未来函数防火墙——守住,且多两道机器闸。** 取数唯一通道=youzid 的 GuardedSource(Python 原样,AsOfGuard 不动);dsh 侧数据工具**不接受日期参数**,as_of 在会话创建时钉入 bridge 配置——结构防御平移:模型在工具 schema 层面就够不到任意日期。交易/refine profile 用白名单组合,不挂 web/bash/fs/subagent 默认工具(minimal.cordis.yml 先例证明可精确排除【S】【G】);keyless 启动测试断言 `ctx.tools.schemas()` 恰为预期集合(目录即由真实 boot 后读 schemas() 生成,证明此断言可写【R/tool-catalog】)。打分延迟不变(Python WalkForwardEval);oracle 标签只走 bridge 命令通道写 stats,永不成为 surface 事件——dsh 的 surface/log-only 二分【R/session】恰好承载"标签留档但不进模型历史"。**新增风险**:防线从单进程类型结构延伸到进程间协议,一旦有人往 profile 加默认工具即破防——用"profile 即代码评审 + schemas() 断言测试"顶住;这是从"frozen 对象够不到"降为"组合+断言够不到",诚实计为轻微弱化。

**② 观测 vs 编辑边界——守住,且更结构化。** 结构编辑唯一入口=9 个 dsh tools→TS 内核→`harness_edit` 表+审计事件,缺 rationale 拒绝(拒绝管线语义全量移植,现有 Python 拒绝测试表即 TS 验收清单)。观测(SkillStats/importance)经 bridge 命令通道(非模型 turn【M:architecture.md】)直写 `skill_stats`/`lesson`,不产生编辑事件;**表级分离**(skill_def 无 stats 列)使 patch 工具物理写不到观测字段——`_PATCH_FORBIDDEN` 从字段黑名单升级为 schema 结构。credit 幂等账本 UNIQUE(trajectory_id) 闭合已知债务。**代价**:迁移期拒绝管线双实现,漂移靠跨语言金样测试压制;waterfall 忘调 `next()` 即静默短路【D/framework/events】是 TS 侧新坑,需 lint/测试盯。

**③ immutable-core——守住,但防线形态变了。** 三层:(a) 密封种子文件随 bundle 只读分发,doctrine 投影渲染时**强制并入** immutable 条目——即使 DB 被越权改也删不掉红线;(b) `rewrite_doctrine`/`remove` 工具对 immutable=True 拒绝(TS 内核);(c) ToolGuard 第二道闸(guard 存在于管线【R/capability-seams】,签名未读 **[假设待验证]**)。**诚实**:Python `__setattr__` 守卫无 TS 直接对等物;补偿是工具参数与会话事件 deep-freeze【R/tools】【R/session】+ 单写者拓扑(仅 refine 会话挂 meta-tools)。进程内任意代码突变的防线弱于 pydantic 守卫——这是本设计的一处真实代价,靠(a)的"渲染时并入"把最坏情形钳为"红线永远出现在模型面前"。

**④ 领域核心纯净——字面改写,精神保住。** Python 剩余核(data/eval/store)零 web/框架依赖不变;youzid 只是薄 RPC 壳,壳依赖领域、领域不依赖壳(现分层原则平移)。TS 侧照抄 dsh 自家纪律:领域逻辑在 `youzi-harness-kernel`(纯 TS 包,不 import cordis),接线在插件与 cordis.yml【M:examples/AGENTS.md】,插件只依赖 Service Definition【M:packages/README】。**诚实**:不变量④的字面是"youzi/ 一包纯净",嫁接后变成"双语言双核、各自纯净、协议缝合"——H 域被移出 Python,这是立场 B 的固有价格,不装作等价。

**⑤ 离线优先——守得住,但 CI 变重。** Python 车道原样(FakeSource/MockLLM/`:memory:`,495 测试不动)。TS 车道:fake LlmAdapter(实现 `stream()` 即可【R/llm-streaming】)或 llm-replay **[假设待验证]**;fake-youzid(同协议内存实现,喂 FakeSource 数据);keyless 测试先例=真 Loader 起 cordis.yml 验输出+干净退出【M:examples】。跨语言金样(同种子+同编辑脚本→H JSON 哈希一致)进 CI。**代价**:CI 新增 Node 22.19+/pnpm 车道;dsh 版本必须钉死 commit(0.0.0.dev0【S】);"永不触网"靠我们的 profile 白名单+断言,不是 dsh 默认(SDK 示例默认 danger-full-access【S】,必须显式收紧)。

**⑥ 人确认下单——守住,且获得更好的 UI。** 结构保证第一条:**全系统不存在下单工具**,缺席即防御(与今天一致)。运营写工具(confirm_decision/record_fill)pre-execute 返回 ask【R/tools】,经 interaction/approval 人审【M:packages】,Web UI 先问再执行【G:quickstart】;profile 钉 approval=ask、禁 never。人确认回流(DAgger 数据)以 approval 结果事件留痕——approval 事件 schema 未核【R 诚实清单】**[假设待验证]**,W3 前必须实读。

## TS/Python 边界协议

- **双拓扑**:运营=dsh-as-host——youzi-bridge 插件 spawn youzid 子进程(`packages/subprocess` 存在【M】),行分隔 JSON-RPC on stdio(与官方 Python SDK 同款传输,先例在库【S】)。研究=Python-as-host——compare_harnesses 经 `deepseek-harness-sdk` 拉起 runtime 子进程【S】,bridge 配置为连回 Python 进程内 youzid 服务的本地 socket。
- **单信道双向**:同一条双工连接承载 dsh→Py(`data.get_state`/`data.get_universe`/`eval.score`)与 Py→dsh(`credit.apply`/`harness.revert`/`refine.trigger`)。两端皆我方代码,**零未验证 dsh API 依赖**;刻意不用 SDK 的 `next_request/respond` 反向通道(存在但无文档背书【S】)。
- **序列化**:全 JSON;frozen 快照整对象传输并采纳 whole-value 规则(状态载荷带完整后像【R/session】);H 版本 content-addressed(sha256);每请求带 `as_of`+`request_id`。
- **失败语义**:youzid 掉线→bridge 撤回服务→依赖工具 fiber 转 PENDING(依赖缺失即静默失活,不误报【D/framework】【P】)→会话取不到数,**fail-closed**;runtime 掉线(研究)→SDK 超时带 exit code+stderr 尾 400 行诊断【S】,该臂作废重跑;写路径幂等键(edit_id/trajectory_id)允许安全重试;交易日游标与评测时钟以 Python 侧为准(评测尺是裁判,永不外包)。

## 迁移波次

**W0 垫片与钉版本(不碰现有代码)**:vendor dsh 钉 commit;youzid 抽壳(在现有 OpsRepository/GuardedSource 后面加 stdio JSON-RPC 入口);协议 schema + fake-youzid;金样测试框架。离线:纯 Python,495 测试不动,无 Node 依赖。回退:删目录,零耦合。

**W1 act 半环上 dsh(研究模式)**:trading profile(白名单工具)、bridge、数据工具、`submit_decision`;新 `DshAgentPolicy` 实现 `DecisionPolicy` 协议——InnerLoop/compare **零改动**即可换臂。离线:Python CI 用 `FakeHarnessPolicy` 替身(协议注入,永不需要 Node);TS 车道 keyless 启动断言工具集恰为预期;LLM 用 fake adapter。回退:factory 换回 `LLMAgentPolicy`,协议未变。

**W2 H 内核 TS 化**:`youzi-harness-kernel` + storage domains + 9 meta-tools + credit 桥 + revert 命令;**双跑影子验证**——同一证据包分别喂 Python Refiner 与 dsh refine 会话,diff 产出的 H。离线:拒绝管线测试表全量移植为 TS 单测;跨语言金样进 CI。回退:H 导出/导入 JSON 双向;Python Refiner 留 flag 后备直到 parity 达标。

**W3 运营模式 dsh-as-host**:schedule+approval+Web UI 接管决策驾驶舱;ops 写工具走 ask;youzi_web 只留 ops 录入页(UI 扩展文档缺失,不强迁)。前置:实读 approval/schedule 子系统页(现为 [假设待验证] 密度最高处)。离线:ops 真相仍在 Python,store 测试不动;approval 流 keyless 可测性验证是本波验收项。回退:youzi_web 驾驶舱与 dsh UI 双跑一个月,同读同一存储,不满意即切回。

**W4 多臂隔离 + 北极星**:每臂独立 runtime 进程 + profile patch + session_root;RunStore 退役(transcript→session log,数值→既定 C 期 research 表);跑真实多窗 HCH vs Hexpert。离线:多臂编排用 SDK 层替身测试。回退:compare_harnesses 原路径因 W1 的协议对等而完好。

## 风险与开放问题

1. **preview 地基**:0.0.0.dev0、SESSION_FORMAT_VERSION=0 无兼容承诺、"随时 breaking"【S】【M:AGENTS.md】。对策:钉 commit;真相只在 storage domain(schema 我方声明)与 Python store,session log 仅审计投影;夜间导出 H 为我方 JSON 格式作逃生舱。
2. **双实现漂移**:拒绝管线/种子 schema 在迁移期两语言并存;金样测试是唯一护栏,W2 未达 parity 前不许下线 Python Refiner。
3. **[假设待验证] 清单(按波前置实读)**:schedule/jobs API(W3)、approval 事件 schema 与 keyless 可测性(W3)、system-prompt 段贡献 API(W2)、llm-replay 细节(W1)、preset 运行时创建(ΔG,W4 后)、ToolGuard 签名(W2)、storage 后端能否收养既有 SQLite 文件(倾向不收养)。
4. **dsh skill ≠ K** 是本设计最大的圆钉方孔:我们只用 skill 体系作投影,不假装语义吻合;若 SkillProvider 接口变动,投影层是唯一受伤面。
5. **UI 缺口**:dsh UI 扩展零文档【D】——ops 录入页可能长期留在 FastAPI,youzi_web 退役是渐进而非一刀。
6. **开放问题**:研究模式 N 臂=N 进程(保守,硬隔离)还是 1 进程 N isolate realm(轻,但 realm 语义为进程内【P】)?refine 证据包经 prompt 注入是否撞 context 上限(compaction 子系统未读)?G 群 8 子 Agent 的成本(每子代理一个 session)在 DeepSeek 计费下是否可承受?
7. **运维重量**:单机单人场景常驻 Node+Python 双进程、双测试车道——若北极星实验证明自进化无 alpha,本嫁接的回报主要剩"运营 Co-pilot 的 UI/审批/审计",届时应重估 W3/W4 是否继续。