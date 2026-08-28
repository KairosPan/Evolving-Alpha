# 嫁接设计:立场 C —— 会话日志中心的两环再表述(youzi × dsh)

> 依据:8 路研究笔记(下文以 [phi]=dsh:philosophy、[gui]=dsh:guide、[sdk]=dsh:python-sdk、[dev]=dsh:develop、[ref]=dsh:reference、[repo]=dsh:repo、[blu]=proj:blueprint、[cod]=proj:code 指认出处)。凡笔记未见的能力一律标 **[假设待验证]**。

## 设计总览(一段话立场)

把"进化"重述为**会话空间上的操作**:act = 一次 append-only 会话(frozen 快照进 prompt、DecisionPackage 出、全程入日志);refine = 一次"批注会话"(读经 Python 评测尺整理过的历史证据包,经 meta-tool 桥发出结构性编辑);H 本身重述为**编年史事件流的纯折叠投影**(seed 事件 + 每日编辑事件 → fold 出 H_t),从而 Hexpert = "只含 seed 前缀、从不追加编辑"的同源分支,rollback = 在历史稳定边界上 fork 再续写,EditGate = 在 fork 出的候选分支上跑影子走查再 adopt。dsh 提供其中"会话运行时"那一半的现成实现——append-only SessionEvent 日志、resume/fork、request/header 全量请求快照、JSONL/SQLite 落盘、Python SDK 子进程驱动([ref][sdk]);而 youzi 的领域内核(防火墙、oracle 打分尺、信用回注、meta-tool 拒绝管线、immutable-core)**一行不迁**,继续做 Python 真相源。关键的诚实前提:dsh 处于 developer preview、`SESSION_FORMAT_VERSION=0` 无兼容承诺([ref][repo]),因此本设计遵循 [repo] 笔记的结论——**preview 期不把 youzi 真相源搬进 dsh session log**:H 编年史与运营/研究数据的真相留在 `youzi/store`(事件 schema 刻意做成与 dsh SessionEvent 同形),dsh 会话日志是 act/refine 对话的**权威留痕副本与审计面**,真相合流是格式稳定后的可选终态。

## 组件映射表

| youzi 现有构件 | dsh 概念([出处]) | 处置 | 理由与诚实度 |
|---|---|---|---|
| `LLMAgentPolicy.decide()`(act 半环) | 一次 session/turn:`harness.run(prompt, session_id)`([sdk]) | **融合** | DecisionPolicy 协议不动,新增 `HarnessSessionPolicy` 实现;dsh 是"带日志的重型 LLM 调用"。真同构。 |
| `llm/client.py` 重试/退避 | runtime 内 LlmAdapter + 重试策略([ref] llm-streaming) | **融合** | act 路径退给 runtime;in-process 路径(Refiner 离线测试)保留原 client。 |
| `llm/cache.py` CachedLLMClient(E1) | replay=重派生请求([ref]);`llm-replay` adapter 存在但未读 | **保留** | **E1↔replay 是半修辞**:dsh replay 重建的是请求不是响应。落地方案:自建 OpenAI 兼容录放代理(Python),经 `base_url`/`DEEPSEEK_BASE_URL` 指入([sdk][gui]);`llm-replay` 语义 [假设待验证]。 |
| `loop/inner_loop.InnerLoop` | 无对应(编排留 Python) | **保留** | 日循环、延迟打分、信用、熔断、水位线全是领域机制([cod]④);只把两处 LLM 调用改指会话。 |
| `loop/compare.compare_harnesses` | 每臂独立 `DeepSeekHarness` 子进程 + 独立 `session_root`/cordis([sdk]);isolate realms([phi]) | **融合** | factory 注入升级为 OS 级进程隔离,防污染更强。realms 属进程内语义,跨进程用不上——引其思想不引其机制。 |
| `loop/run_store.RunStore` | dsh 会话转录(JSONL/SQLite)([ref] persistence)+ store C 期 `research_run` 表([cod]③) | **退役** | 与既定 spec 方向一致:结构化结论进 SQLite,原始对话留痕归 dsh transcripts。 |
| `harness/snapshot+manager`(checkpoint/rollback) | `fork(source, boundary)`,boundary 须"turn 间稳定位置"([ref] session) | **融合** | checkpoint=记录编年史 seq;rollback=在该 seq fork 出新分支头,旧时间线保留可审计。fork 的"稳定边界"约束与 pre-refine checkpoint 语义**真同构**;但 rebind 契约不消失,变为"fork 后重折叠 H + factory 重建 agent/refiner"([cod]④)。 |
| `harness/edit_log.EditLog` | refine 会话内 tool/call+tool/result 事件流([ref]);"Model-visible means logged"([repo]) | **融合** | **痕迹层真同构、真相层修辞**:refine 会话日志天然记录每次 meta-tool 调用及 rationale,但格式 v0 无兼容承诺 → 真相仍在 `harness_edit` 表(D 期),会话日志为影子,加一致性断言。 |
| `harness/metatools.py` 9 算子 + 拒绝管线 | dsh tool(`defineTool`)是模型侧入口([dev]);校验执行在 Python | **保留(原样)** | 全拒/不半应用/不崩的拒绝管线是领域不变量②③的执行体,绝不重写为 TS。dsh 侧只是薄代理。 |
| `refine/credit.apply_credit` | projection 的 whole-value 事件规则([ref] session-projection) | **保留+改造** | 直写语义不变;事件化为"携带完整后像 + trajectory 幂等键"的观测事件,顺手闭合"apply_credit 无幂等守卫"隐患([cod]②)。真同构且是白捡的修复。 |
| `eval/`(oracle/scorer/fill/stats) | 无对应 | **保留(原样)** | dsh 没有任何"决策好不好"的领域尺([dev] 启示 3)。 |
| `data/`+`replay/`(GuardedSource/AsOfGuard/PIT parquet) | 无对应 | **保留(原样)** | 防火墙三重防御是头号铁律;PIT parquet 真相不动([cod]②③)。 |
| `agent/parse.py` 幻觉过滤/空仓兜底 | 无对应 | **保留(原样)** | "LLM 输出一律不可信"对 `final_response` 同样成立。 |
| `harness/` p·K·M·regime | p→我们自渲染 system prompt(经 `DSH_SYSTEM_PROMPT`/组合配置 [sdk][gui]);K→SkillProvider 动态供给([dev][ref] skills) | **保留+投影** | dsh skill 是静态指令文件、无 SkillStats/生命周期/信用([dev] 启示 3)——K 的真相与进化留域内,dsh skills 只是"现役技能渲染后的只读投影"。M 同理(证据包内注入)。 |
| immutable doctrine 守卫 | 无对应 | **保留(原样)** | 见不变量③。 |
| `youzi/store/` 运营 7 表 + OpsRepository | dsh storage 子系统存在([ref] storage) | **保留** | 运营真相绝不进 dsh;`domain/changed` 仅进程内、跨语言须走持久层([ref] 风险)。 |
| `youzi_web/`(FastAPI+HTMX) | `dsh web` UI + 会话检索([gui][repo]) | **分阶段退役** | B-web 运营录入页保留(写路径经领域命令 API);研究/会话查看长期由 dsh web 替代——但 UI 扩展文档缺失([dev] 未查明),节奏见波次,含 [假设待验证]。 |
| G 子 Agent 群(蓝图目标态,现为 no-op) | `dsh-tool-subagent` + `subscribe_session_notifications` 子孙树归并([sdk][ref]) | **融合(未来)** | 8 具名子 Agent([blu]④)映射为子会话树,事件自动归并入父臂审计。这是嫁接后 ΔG-pass 脱离占位的最短路径。 |
| A2 EditGate(待做) | fork 出候选分支 + 影子走查([ref] session;机制自建) | **新建** | 见总览与波次 3。**"在 fork 上验收"是真同构,"adopt"是修辞**:dsh 无 merge 原语,adopt=把候选编辑事件重放到主编年史,弃分支。 |

**映射诚实度小结**:真同构——act=会话、fork 边界=checkpoint 稳定点、whole-value 投影=H 折叠/信用幂等、request/header=H 渲染审计、surface/log-only 二分=观测/编辑二分([ref] 启示 5)。半同构——EditLog(痕迹是、真相否)、Hexpert=fork(对**编年史**成立,对逐日 act 会话只是"每臂一族会话"的记账修辞)、E1↔replay(精神同、机制异)。纯修辞——"refine 直接读历史会话":refine 实际消费的是 Python 评测尺整理的证据包(oracle 标签根本不在 act 会话日志里,也不该在),不是裸会话回读。

## 运行时架构

```
┌─ Python 主进程(orchestrator,youzi 全域逻辑) ──────────────────────────────┐
│  InnerLoop / compare_harnesses(不变)                                       │
│  ┌───────────┐   frozen MarketState/Universe    ┌──────────────────────┐    │
│  │ data/replay│──(GuardedSource, ≤t)──────────▶│ HarnessSessionPolicy │    │
│  │ PIT parquet│                                 │ (DecisionPolicy 实现) │    │
│  └───────────┘                                  └──────────┬───────────┘    │
│  eval 延迟打分 → apply_credit(whole-value 幂等事件)→ B2 熔断              │
│  Refiner 编排:证据包组装 → refine 会话 → meta-tool 拒绝管线(Python)      │
│  youzi/store SQLite:ops 7 表 · research · harness_version/edit(=H 编年史真相)│
│  H_t = fold(编年史事件);rollback = fork@seq + 重折叠 + factory rebind      │
└───────┬──────────────────────────────┬──────────────────────────────────────┘
        │ SDK: stdio JSON-RPC(子进程,每臂一个)[sdk]          ▲
        ▼                              ▼                       │ HTTP/CLI(仅 refine 会话)
┌─ dsh runtime(臂 HCH)─────┐  ┌─ dsh runtime(臂 Hexpert)─┐  │
│ act 组合:llm-deepseek +   │  │ act 组合同左(无 refine    │  │ meta-tool 桥:
│  sdk-jsonrpc,零工具/禁网  │  │  会话,无编辑事件追加)     │  │ dsh tool → youzi
│ refine 组合:+ meta-tool 桥│  └───────────────────────────┘  │ 命令 API(校验在 Python)
│ session_root/HCH/*.jsonl   │   session_root/Hexpert/*.jsonl  │
└──────────┬────────────────┘                                  │
           └── LLM 出站 → base_url ⇒ Python 录放代理(E1)⇒ DeepSeek API
```

数据流(一日):① orchestrator 经 GuardedSource 造 frozen 快照 → 渲染 H_t 进 prompt → `run(prompt, session_id="HCH/2026xxxx/act")`;runtime 内一个 turn(零工具),`final_response` 回 Python,`RunResult.events` + `session.event` 通知全量留痕([sdk])。② parse → DecisionPackage → 延迟打分 → apply_credit(观测事件,幂等键)→ 熔断评估。③ 触发 refine 日:orchestrator 组证据包(A3 水位线切片 + credit 报告 + 失败签名,均 Python 产)→ `run(evidence, session_id=".../refine")`,refine 组合暴露 9 个 meta-tool 桥工具;每次调用穿 dsh tools waterfall(pre-execute 可 ask)([dev])→ 落到 Python 拒绝管线 → 通过则写 `harness_edit`(真相)+ 编年史追加事件;会话日志自动持有同一串 tool/call 痕迹。④ 次日 fold 出 H_{t+1}。熔断触发:定位退化窗前最近 checkpoint seq → 编年史 fork@seq → 重折叠 → factory 重建 agent/refiner(rebind 契约保留,[cod]④)。

## dsh 买到了什么

1. **append-only 类型化会话日志**:SessionEvent(type/seq/time/data)、seq 连续、深冻结、`deriveMessages()` 派生模型历史([ref] session)——act/refine 全程留痕不再自建。
2. **"Model-visible means logged" 运行时断言**([repo])——"进模型的必可从日志重建"从评审纪律变成机器保证,是防火墙的**事后审计面**(见不变量①)。
3. **request/header EpochHeader 全量请求快照**([ref])——每次 loop 记录 config/system/tools 完整后像,正是 [ref] 启示 4 说的"live H 渲染进 prompt 的审计对偶":HCH vs Hexpert 的每一次决策请求可逐字重建。
4. **fork(boundary)/parentSession/seedLength + resume/崩溃恢复**(未闭合 turn 合成 `turn/end{interrupted}`)([ref] session/persistence)——多窗长跑可断点续跑;EditGate 沙箱与 rollback 的分支语义现成。
5. **projection 子系统**(init/apply 纯折叠、whole-value 规则、snapshot/restore/stateVersion)([ref] session-projection)——H-as-fold 与信用幂等的形式模板,直接照抄其事件规则。
6. **Python SDK**:子进程 stdio JSON-RPC、同步 turns API、`RunResult.events`、`on_notification`、`subscribe_session_notifications` 子孙会话树归并([sdk])——编排接线零自研,子 Agent 树审计白送。
7. **tools waterfall 管道**(pre-execute allow/deny/**ask**、guards)([dev])——meta-tool 桥的机器闸;六道闸中"人审"有现成挂点([dev] 启示 2)。
8. **SkillProvider 动态供给**(`registerProvider`)([dev][ref] skills)——K 现役集渲染为 skills 暴露给模型,[dev] 笔记明言这是"最顺的嫁接点"。
9. **两种转录后端**(JSONL zstd 帧/raw lines、SQLite)([ref] persistence)——留痕存储免费;JSONL 格式公开可跨语言读([repo] 启示)。
10. **组合即配置**:cordis.yml 逐件声明、显式关插件(minimal 例即关 skills/触网件)([sdk][gui])+ preset 按会话合成 agent([repo])——act/refine/各臂三种组合三份 YAML。
11. **审批 seam**:`interaction` 包(approval/permission/ask-user)([repo])——决策确认 UI 的长期宿主。
12. **`dsh web` 会话检索 UI**([gui][repo])——研究回看界面;但**面板扩展方式文档缺失**,深度定制 [假设待验证]。
13. **`llm-replay` adapter**([ref] capability-seams,页面未读)——响应级回放的官方候补,语义 **[假设待验证]**;自写 LlmAdapter(`stream()` 契约有文档 [dev])是备选。

## 六条硬不变量逐条论证

**① 未来函数防火墙 —— 守住,且升级为可审计。** 结构防御原封:快照仍由 Python 侧 `GuardedSource` 产出,frozen 无句柄,dsh runtime **从头到尾不持有任何数据源**——它只收到 prompt 文本。act 组合裁到零工具、无 web/fs 插件(cordis 显式关,[sdk][gui] minimal 例先例;"零工具组合可行"依据"一切皆插件"哲学推断,[假设待验证])+ sandbox `read-only`([gui])。oracle 标签只进 refine 会话的证据包(t+horizon 后),永不进 act 会话——由编排保证,且新增一个**日志 lint**:扫描 act 会话事件流断言无标签类事件、`request/header` 快照中 system prompt 与我们渲染的 H 逐字一致(能力 2/3 使此断言可机器执行)。净变化:防火墙从"结构+评审"变为"结构+评审+事后日志证明"。

**② 观测 vs 编辑边界 —— 守住,借 surface/log-only 二分强化。** 结构性编辑:唯一入口仍是 Python 9 算子拒绝管线;refine 会话中的桥工具只是运输层,校验/落库在域内;真相入 `harness_edit`(带 rationale),会话日志的 tool/call 流是影子痕迹,波次 2 加"影子↔真相"一致性断言。观测直写:apply_credit 语义不变、不入 EditLog;事件化后标记为编年史的 **log-only 观测事件**(不参与"编辑史"派生),与 dsh surface/log-only 二分一一映射([ref] 启示 5)。whole-value+幂等键顺带闭合重复累加隐患。代价诚实说:边界在**两处**表达(域内 `_PATCH_FORBIDDEN` 强制 + 事件分类),需一条架构测试钉住两者同步。

**③ immutable-core —— 守住,原样。** `DoctrineEntry.__setattr__` 守卫 + `Doctrine.rewrite/remove` 双拦截不动;桥工具无新增权能(它只能到达拒绝管线,而管线对 immutable 全拒)。新增一层:H=fold 之后,**折叠函数本身重校验**每条编辑事件——即便有人绕过管线伪造编年史事件,fold 时对 immutable 目标拒绝入账。防线从 2 层变 3 层。

**④ 领域核心纯净 —— 守住。** `youzi/` 零新增依赖;全部 dsh 接触面收进新包 `youzi_dsh/`(地位同 `youzi_web`:单向依赖领域、只经协议注入)。`HarnessSessionPolicy` 实现既有 `DecisionPolicy` 协议;`deepseek-harness-sdk` 只在 `youzi_dsh` 内 import 且懒加载(照抄 akshare/openai 末端懒加载惯例 [cod]⑤)。架构测试断言 `youzi/` 无 `youzi_dsh`/`deepseek_harness` import。

**⑤ 离线优先 —— 守住,靠协议替身,不靠 dsh。** 新增窄协议 `SessionRunner`(`run(prompt, session_id) → SessionResult{final_response, events}`),`youzi_dsh` 的真实现包 SDK,测试用 `FakeSessionRunner`(脚本化返回 + 录制的 events fixture,JSONL raw lines 格式公开 [ref] 可造)。**CI 永不 spawn runtime 二进制**——SDK 需真二进制([sdk]),故集成冒烟归 `scripts/smoke_dsh_*.py` 手动位。E1 录放代理本身纯 Python 可离线测。诚实代价:与 MockLLM 盲区同构([cod]⑤),离线测得了编排正确性、测不了 dsh runtime 真行为;这不是新债,是旧债换了债主,冒烟脚本是既有解法。

**⑥ 人确认下单 —— 守住,平凡且加固。** 任何组合里都不存在下单工具——不变量由"工具不存在"结构保证;确认写路径仍是 `OpsRepository.confirm_decision`(B-web 录入页)。加固项:refine 编辑的 adopt 可选挂 tools pre-execute `ask` 闸([dev]),把"人确认"从下单扩展到"人批准打法变更"(EditGate 人工档);approval 默认 fail-safe 与 dsh 权限哲学同向([gui])。**必须显式规避**:SDK 示例默认 `danger-full-access` + 继承全环境([sdk]),我们的 cordis 组合一律显式收紧。

## TS/Python 边界协议

- **进程模型**:Python orchestrator 常驻;每臂一个 `DeepSeekHarness` 上下文管理器(独立子进程、独立 `cwd`/`session_root`/`cordis`/`env`,[sdk])。通信 = stdio 上行分隔 JSON-RPC 2.0,SDK 纯同步+线程,无 asyncio([sdk])——与 InnerLoop 的同步日节奏合拍。臂间隔离在 OS 进程级,factory 契约升级不废除。
- **谁调谁**:Python→dsh:turn 驱动(`initialize`/`session/prompt`/`shutdown`,[sdk])。dsh→Python:仅 refine 会话内,经桥工具;**波次 2 用 bash 工具跑 `youzi-metatool` CLI**(最朴素、有文档背书的路径 [sdk] 启示 2),契约:stdin JSON `{op, target, payload, rationale}` → stdout JSON `{accepted|rejected, reason}`,exit code 非 0 = 桥故障(≠拒绝)。目标态换 TS `defineTool` 代理 → 本地 FastAPI 命令 API(TS 侧 `defineTool` 有文档 [dev];HTTP 跳自建)。反向通道 `next_request/respond` 存在但无文档用例([sdk]),**[假设待验证]**,不作依赖。
- **序列化**:入 = prompt 纯文本(H 渲染 + frozen 快照 JSON 内嵌);出 = `final_response` 文本,走既有 `agent/parse`(不可信输入原则不变)。事件流经 `on_notification`/`RunResult.events` 收取(`session.event`/`turn/end`/`subagent.*` method 名见 [sdk]);跨语言**不依赖** runtime 进程内事件总线([ref] 风险),必要时直读 JSONL 转录。
- **失败语义**:act 会话超时/崩溃 → SDK raise(带 stderr tail 诊断 [sdk])→ 编排按"LLM 失败"处理 = 空仓兜底,session_id 加 attempt 后缀重试,废会话留档;refine 会话失败 → 当日跳过 refine(H 不变),与"全拒不崩"同语义;runtime 中途死 → dsh 崩溃恢复合成 interrupted turn/end([ref]),编排以日为幂等单元重跑。
- **版本钉死**:SDK `0.0.0.dev0`、版本随 Node 主 repo 浮动([sdk])→ requirements 精确 pin + `SessionRunner` 薄适配隔离 API 漂移;事件 method 名视为不稳定,fixture 录制带版本戳。

## 迁移波次

- **波次 0(前置,零 dsh 依赖)——H 事件化**。D 期 `harness_version/harness_edit` 落地时按 SessionEvent 同形 schema(type/seq/time/data)+ whole-value 后像 + trajectory 幂等键实现;`H = fold(events)` 与 `SnapshotStore` 双跑对账一个窗口后切换;rollback 改为 fork@seq。离线可测:纯 Python,新增 fold/幂等/fork 单测,495 测试全绿为门。回退:保留 SnapshotStore 读路径,一个 flag 切回快照式。
- **波次 1——act 外包**。新包 `youzi_dsh/`:`SessionRunner` 协议 + SDK 实现 + `FakeSessionRunner`;`HarnessSessionPolicy` 进 compare 作新臂与 `LLMAgentPolicy` **同窗对跑**(同一评测尺,先证不劣再切换);E1 录放代理上线(`base_url` 指入)。离线可测:Fake runner + 录制 fixture,CI 零 runtime;真实冒烟 `scripts/smoke_dsh_agent.py`。回退:DecisionPolicy 协议下换回原实现,一行配置。
- **波次 2——refine 会话 + meta-tool 桥**。`youzi-metatool` CLI(纯域内逻辑重打包,先独立测)→ refine cordis 组合(bash 桥)→ InnerLoop 的 refine 步改走会话;影子↔真相一致性断言上线。离线可测:CLI 直测拒绝管线全用例;会话层用 Fake runner 脚本化 tool-call 序列;原 in-process Refiner 路径**保留**为离线测试与回退双用途。回退:`enable_refine` 走旧 Refiner。
- **波次 3——EditGate(A2)落地为 fork 验收**。候选编辑先落编年史 fork 分支 → 影子走查:近 N 日用候选 H 重决策(经 E1 代理,新 prompt 必 miss → 真 LLM,成本按 N 封顶)→ 同 oracle 已实现结果打分,对比现役 H 同窗 advantage → 达标 adopt(重放事件到主线)/ 不达标弃分支;可选人工 ask 档。离线可测:MockLLM/Fake runner 测闸机器全逻辑(通过/拒绝/平局/成本封顶)。回退:闸关 = 现行"直接生效"行为。
- **波次 4(可选,格式稳定门)——真相合流 + UI 收编**。`SESSION_FORMAT_VERSION>0` 且升级路径明确后:编年史/转录迁 dsh SQLite 持久层,`dsh web` 接管研究回看,`youzi_web` 收缩为运营录入。此前 dsh 侧永远只是副本。回退:默认态即回退态(store 为真相)。

## 风险与开放问题

1. **preview 不稳定是首要风险**:`0.0.0.dev0`、`SESSION_FORMAT_VERSION=0`、官方明示随时 breaking([sdk][ref][repo])。对策已内建(真相不迁、薄适配、版本 pin),但波次 1-3 的返工概率仍非零。
2. **决策温度与确定性**:smoke_compare 依赖 temp=0.0;SDK config 未见 temperature 字段([sdk]),cordis 组合能否按臂设温未查明——**开放问题**,冒烟首日必须核。
3. **零工具 act 组合可行性 [假设待验证]**:minimal 例最少也带 bash+editor([sdk]);若 agent-loop 拒绝零工具,退路是给一个只读空 workspace(防火墙不破,审计面稍脏)。
4. **prompt 纯净性**:dsh 自身可能注入 system 段(system-prompt 子系统 [dev]);其快照测试文化("插件偷加上下文即 fail" [sdk])+ 我们的 request/header lint 是对策,但注入面全貌未查明。
5. **`llm-replay`/Python 侧工具注册/UI 扩展**三处官方文档空白([ref][sdk][dev] 未查明清单)——分别有备选(自建代理/CLI 桥/保留 youzi_web),不构成阻断但压缩了立场 C 的理想形态。
6. **EditGate 影子成本**:每次验收 N 日真 LLM 重决策,费用与延迟需预算化(N、触发频率、仅高风险编辑触发的分级策略——开放调参)。
7. **诚实的总代价**:本设计买到的是**会话运行时与审计面**,不是 alpha。北极星问题(HCH 能否胜 Hexpert)与嫁接正交;嫁接不应阻塞既定的真实多窗对比——波次 1 的"同窗对跑"设计刻意让北极星实验可在旧路径先跑。
8. **平台约束**:SDK 不支持 Windows、macOS 14+ arm64([sdk])——当前开发机(darwin)符合,部署面收窄需记录。