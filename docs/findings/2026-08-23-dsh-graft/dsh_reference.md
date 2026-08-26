# dsh(DeepSeek Harness)API 参考尽调笔记

来源根:`REF = https://deepseek-harness.github.io/deepseek-harness/en/reference/`。共实读 13 页(索引、session、persistence、persistence-catalog、tool-catalog、config-catalog、agent-lifecycle、session-projection、skills、capability-seams、storage、llm-streaming)。文档为 developer preview,`SESSION_FORMAT_VERSION = 0`("pre-release, no compatibility implied")。

## 核心概念

- **Cordis 插件组合**(`REF`):整个平台是分层 bundle 从空态叠加组合(base bundle → profile patch → home patch → CLI overlay,叠加式变换)。为什么:任何组件可经配置替换,不 fork 上游。
- **Service 三分类**(`REF/capability-seams`):`core`(唯一 owner 单例,如 `ctx.sessions`/`ctx.tools`/`ctx.agents`)、`seam`(可换实现的能力缝,如 `ctx.llm`/`ctx.sessionPersistence`/`ctx.storage`)、`bundle`(组合点,如 `ctx.agentLoop`)。为什么:换一个 provider(如 subprocess-local→subprocess-e2b)能力级联到所有依赖方。
- **Session = append-only 事件溯源日志**(`REF/subsystems/session`):`Session` 是普通类(非 Service),持有类型化 `SessionEvent` 的连续 seq 日志;事件 append 时深冻结、必须 JSON 可序列化。LLM 消息历史是从日志**派生**的,不单独存。为什么:"model-visible means logged"——凡进模型的必须可从事件流重建,保可复现与审计。
- **Surface 投影**(`REF/subsystems/session`):日志分两类事件——surface 事件(`user/message`/`assistant/message`/`tool/result`,产生派生消息,带 `surfaceOp: 'append' | {op:'replace',start,end}`)与 log-only 事件(turn/step 边界等,只留档不进模型历史)。compaction 用 `replace` 遮蔽旧节点。
- **Projection = 纯函数折叠**(`REF/subsystems/session-projection`):领域插件定义 `init()`/`apply(state,event)` 纯转移,框架驱动;whole-value 事件规则(状态事件携带完整后像,绝不发裸 delta)。
- **Agent 双层事件**(`REF/agent-lifecycle`):`session/event` = 持久可回放事实;`agent/*` = 活体协调 API(队列/状态/prompt 拦截/steering)。
- **Skill = 文件即技能**(`REF/subsystems/skills`):`<name>/SKILL.md` 或 `<name>.md`(kebab-case),frontmatter 控制 model/user 可调用性;六级来源按 rank 覆盖(项目 `.dsh/skills` rank 100 最优先 → bundled 600)。
- **Storage = hub + backend + domain 三层**(`REF/subsystems/storage`):`ctx.storage` 只是会合点不做 IO;backend(json/sqlite)拥有介质;`ctx.storageDomain` 以 `DomainSpec`(name/version/tables schema)声明领域表,写入排队原子、durability→内存→事件的顺序。

## 关键 API·配置·扩展点(仅写实读到的)

**Session 对象**(`REF/subsystems/session`):
- `class Session { get surface(); readonly header: SessionHeader; get id(); readonly firstLiveSeq; get events(); get seq(); static create(id, seed?, header?); static fromRestore(id, seed, header); append<T>(type, data, ...opts); requestHeader(): EpochHeader|undefined; requestContext(); deriveMessages(): Message[]; deriveEventMessage(event) }`
- `SessionEvent = { type, seq, time, data, ignorable?, sourceEventSeqs?, surfaceOp? }`;`seq = log.length` 连续单调。
- 核心事件词表:`turn/start {turn}`、`turn/end {turn, reason}`、`step/start`、`step/end`、`user/message`、`assistant/message {turn,step,message,usage?,interrupted?}`、`tool/result {turn,step,message,error?,meta?}`、`assistant/chunk {turn,step,chunk}`(逐 token 留档、派生时跳过)、`request/header {header,reason}`(每 loop 实例全量快照)、`request/context {provider,model,contextWindow?}`、`session/end-seed`(种子结束标记)、`todo/write`。全目录 60+ 类型见 `REF/persistence-catalog`(生成物,下游插件可 merge 新类型)。

**resume / fork / replay**(`REF/subsystems/session` + `REF/subsystems/persistence`):
- `ctx.sessions`:`create(id?, options?)` / `prepare(id?, options?)` / `enter(session)` / `announce(session)` / `fork(source, boundary?, childSessionId?)` / `flush(session): Promise<boolean>` / `get(id)` / `list()`。
- **fork 语义**:前缀须"end outside an open turn";深克隆种子事件建活体子会话,子 header 带 `parentSession`/`seedLength`/继承 `cwd`;`boundary` 为含端的源 seq,可从任意稳定的 turn 间位置分叉。
- **resume**:持久层 `load(id)`(活体等 durable)/`inspect(id)`(冷读)→ `Session.fromRestore`;崩溃恢复对未闭合 turn 合成 `turn/end {reason:{kind:'interrupted'}}`。恢复时定位**最后一个** `session/end-seed`;重开未动过的会话不增长日志。
- **replay**:回放 = 从同一事件重新派生(`deriveMessages`);projection 侧 `ctx.sessionProjections.snapshot(session)` / `restore(checkpoint, events, baseSeq)` / `restoreFloor(checkpoint)`(锚在最低可用水位线**下一格**以侦测 crash-repair 缩日志);`stateVersion` 不匹配则从 seq 0 全量重折。另有 `llm-replay` adapter 实现(`REF/capability-seams`,细节未读)。
- 持久层抽象(`REF/subsystems/persistence`):`locate(meta)` / `create(meta)` / `append(id, events)` / `prepare(id, signal?)` / `load(id)` / `inspect(id, signal?)` / `readFrom(id, fromSeq, signal?)` / `list()` / `listSnapshots()`;`SessionHeader = { version, id, createdAt, cwd?, parentSession?, seedLength?, origin?:'subagent', delegationDepth?, agentPreset? }`(元数据不入 SessionEventMap)。两后端:JSONL(每会话一个逻辑 JSONL,默认校验和 Zstandard 帧)与 SQLite(schema 17,`node:sqlite`,chunk 按 delta-run 分表存)。

**LLM**(`REF/subsystems/llm-streaming`):
- `Message = { id, role:'system'|'user'|'assistant', content: ContentBlock[], source }`;ContentBlock:text/reasoning/image/tool-call/tool-result(可 merge 扩展)。
- `StreamChunk` 封闭判别联合:`block-start`/`text-delta`/`reasoning-delta`/`tool-call-delta`(参数始终原始 JSON 字符串)/`block-end`/`usage`/`finish {reason, replayState?}`。
- `abstract class LlmAdapter { providerInfo(p); providerRetryPolicy(p); listModels(p); resolveModel(p, m, signal?); abstract stream(options: GenerateOptions): AsyncIterable<StreamChunk> }`;一次 adapter 调用=一次 provider 尝试(库级重试关闭);`streamIdleTimeoutMs` 默认 5 分钟;标准错误码 `CONTEXT_WINDOW_EXCEEDED`/`EMPTY_RESPONSE`。
- `ctx.llm`:`registerAdapter(providers, adapter)`(返回可 `replace(providers)` 的句柄)/ `listProviders()` / `registerConfigurableProviders(entries)` / `resolveModelInfo(p,m,signal?)` / `prepareCall(config, signal?)` / `stream(options)`。`GenerateOptions = { provider, model, reasoningEffort?, messages, system?, tools?, temperature?, maxTokens?, stop?, signal?, sessionId?, purpose?:'compaction'|'session-title' }`。事件:`llm/adapters-updated`、`llm/stream`(waterfall 拦截,loop 构造的请求深冻结)。

**Tool**(`REF/tool-catalog`):经 `ctx.tools` 注册 `{name, description, parameters: JSON Schema}`;目录由**真实 boot 插件后读 `ctx.tools.schemas()`** 生成(schema 依赖运行时配置/动态枚举/MCP)。核心包:`dsh-tools`(`run_code` TS 执行)、`dsh-tool-bash`(每调用新 shell,`run_in_background` 返回 job ID)、`dsh-tool-fs`(read/edit/write)、`dsh-tool-subagent`(隔离委托,toolName 可配)。调用管线:"pre-policy → monotonic guards → around dispatch → post-policy → final-result observation"(`REF/capability-seams`)。

**Skill**(`REF/subsystems/skills`):`ctx.skills`:`registerProvider(create)` / `register(skill)` / `list(options)` / `snapshot(options)` / `get(name, options)`(全定义不缓存);`SkillProvider = { name, list(options), get(candidate, options) }`;config:`collectCacheMaxEntries?` / `bundledSkillDir?`(env `DSH_BUNDLED_SKILL_DIR`)/ `customSkillDirs?` / `catalogDescriptionMaxLength?`(默认 500);事件 `skills/change`;模型侧 `skill({name})` 工具返回 `<skill_content>`/`<skill_resources>`/`<skill_instructions>` 包裹内容;目录变化以 `<available_skills>` 标签间的持久 replacement 注入。

**Storage**(`REF/subsystems/storage`):`ctx.storage.register(name, backend)` / `mount(form, facility)` / `form(form)`;`StorageBackend = { kv?: KvFacet, close() }`;`defineDomain(spec)` / `domainTable<K,V>(schema)`;`Domain`:`table(name)`、`put`/`delete`/`update(key, fn)`(原子读改写)/`global.set`;事件 `domain/changed`(durable 后发,仅进程内)。错误码:`version-mismatch`/`malformed-medium`/`invalid-record`/`already-open`/`backend-not-found`/`facet-unsupported`。

**配置 schema**(`REF/config-catalog`):文件 `cordis.yml`,YAML 分层插件声明 + 每插件 `config:` 块(即其 `apply`/构造器收到的类型);省略字段用插件默认,显式 `false` 关可选功能;凭证字段默认走 env(如 `DEEPSEEK_API_KEY`),**按请求时解析**而非加载时;runtime-only seam 不可在 yml 设;依赖以 "Requires: agents, llm, tools" 声明,由父组合提供。目录由 `scripts/gen-config-catalog.ts` 生成、`pnpm run verify-config-catalog` 校验。

## 设计哲学(关键原文)

- "Model-visible means logged" —— 进模型上下文的信息必须可从事件流重建;这是整个系统的第一公理。
- "The LLM message history is _derived_ from the log, never stored separately; replay is re-derivation from the same events." —— 回放不是重放请求,是重跑同一纯派生。
- "Seq must stay contiguous, so chunks cannot be filtered out of the canonical log." —— 保真优先于日志体积。
- "The whole-value event rule is load-bearing: a state-carrying log event carries the complete post-change state, never a bare delta." —— 状态事件全量后像,消费端 last-wins,转移廉价。
- "The hub performs no IO itself: backends own media, data forms own semantics, and product packages never touch backends directly." —— 三层存储分权。
- "Configuration carries references to secrets; providers own the values… a rotated credential reaches the very next request." —— 配置持引用不持值。
- "SDK users that need replayable transcript data should consume `session/event`; `agent/*` is the live coordination API." —— 持久事实与活体协调严格分频道。

## 对"把一个 Python 领域系统嫁接到 dsh 上"的启示

1. **对齐处惊人多**:dsh 的 append-only SessionEvent 日志 ≈ youzi 的 EditLog+审计不变量;`session/end-seed` + `fork(boundary)` ≈ `HarnessManager.checkpoint/rollback_to`(fork 只许在"稳定 turn 间位置"= 我们的"rollback 后必须 rebind"同源);projection 的 `init/apply` 纯折叠 ≈ 把 H 状态建成日志派生物。若嫁接,H 的结构性编辑可落成自定义 SessionEvent 类型(目录明说"downstream plugin can merge further event types")。
2. **嫁接面是 seam 而非代码移植**:dsh 是 TypeScript/Cordis 生态,Python 领域逻辑最现实的接入点是(a)自定义 `LlmAdapter`(仅需实现 `stream()`)把决策管线伪装成 provider;(b)`SkillProvider` / `.dsh/skills` 目录把打法文档暴露为 skill;(c)`dsh-tool-subagent`/`subagent-acp` 式外进程委托(ACP 实现存在,细节未读)。没有读到任何 Python 进程内嵌入 API。
3. **whole-value 事件规则值得直接抄**:youzi 的 SkillStats/importance 更新若事件化,应发完整后像而非增量——dsh 用它换来"checkpoint 折叠 + stateVersion 失配全量重折"的廉价恢复,正好解决我们 `apply_credit` 无幂等守卫的隐患。
4. **request/header 全量快照 = 我们的"live H 渲染进 system prompt"的审计对偶**:每个 loop 实例记录 `EpochHeader{config,system,tools}`,使任意历史决策的完整请求可重建——HCH vs Hexpert 对比若要可审计,应照此把渲染后的 H 快照入日志。
5. **观测 vs 编辑边界的同构**:dsh 的 surface(进模型)/log-only(仅留档)二分,与我们"观测直写不入 EditLog / 结构编辑必经 meta-tool"边界同构,嫁接时两套边界可一一映射。
6. **风险**:格式版本 0、无兼容承诺;SQLite 后端"rejects older schemas without migration";凭证/事件系统均 Node 进程内语义(`domain/changed` 不跨进程)——跨语言桥必须走持久层(JSONL 文件格式公开:校验和 Zstandard 帧或 raw lines)而非事件总线。

## 未查明/文档缺失

- **agent-lifecycle 页面稀疏**:只有 Mermaid 序列图与导语,`agent/*` 事件确切签名"live in the generated Cordis catalog",未获得 Agent 状态枚举/方法签名。
- **Cordis Core API 六页未读**(Context/Events/Fiber/Registry/Service/Inherited,`REF/cordis-api/*`)——插件 `apply` 签名、inject 声明语法未经一手核实。
- **`cordis.yml` 完整实例缺失**:config-catalog 只给模式与原则,未见一份端到端真实配置文件。
- **`llm-replay` adapter、`subagent-acp`/`subagent-codex`、`session-query`、`compaction`、`approval`、`workflow` 各页未读**(超出抓取预算),仅从 capability-seams 表得知存在;URL:`REF/subsystems/{session-query,compaction,approval,workflow,subagent}`。
- **resume 的用户级入口**(CLI `--resume` 之类)未在参考区见到;只读到了存储层 `load/inspect/fromRestore` 机制。
- **60+ 事件类型的逐条 data schema** 在 persistence-catalog 页有,但本次只取到分类表,未逐条抄录(approval/hook/subagent/team 等类目字段未核实)。
- 未做 WebSearch 补官方公告;以上全部为官方文档一手信息,无二手来源混入。