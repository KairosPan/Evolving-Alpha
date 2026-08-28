# dsh(deepseek-ai/deepseek-harness)仓库内部架构尽调笔记

> 状态:developer preview(README 自述,快速迭代、随时 breaking)。默认分支为 **`master`**(非 main;抓 main 会 404)。repo 元数据:MIT、topics=`ai-agents, cordis, dsh, dsh-plugin`、创建 2026-08-13、最近 push 2026-08-21。TypeScript/pnpm monorepo + 少量 Python/native。

## 核心概念(是什么 / 为什么)

- **Cordis 内核,"everything is a plugin"**:仓库口号即 repo description。架构文档原文:"Cordis is the framework under dsh: plugins contribute services, typed events, and reversible effects to a shared context." 模型适配器、工具注册表、session 日志、agent loop 本身全是可替换插件——**没有特权 core 可改**,新行为一律走扩展点("Plugins, not loop changes",AGENTS.md)。为什么:让框架自身可被 agent 运行时自改(有 `self-modification` 包和 `demo:cordis` 演示"agent 修改自己的 live plugin runtime")。来源:`raw.../master/docs/architecture.md`、`raw.../master/AGENTS.md`。
- **Profile / Bundle 装配**:"A **profile** is a named composition stored in the Harness home. It lists the bundles it stacks… and keeps the user's own `cordis.patch.yml`";"A **bundle** is a distribution format for Cordis config rows and the code they mount, so whatever it inserts stays patchable by the layers above it." 叠层顺序:bundle 按 profile 声明顺序 → profile 的 `cordis.patch.yml` → home 级 patch → `--patch` overlay。基座 bundle `dsh-base` = "model adapters, tools, persistence, sandbox and approval policy, settings, credentials, telemetry";其上 `dsh-web-app`(浏览器应用)/ `dsh-headless`(一次性 runner)。`package.json` 的 `dsh` 字段声明 `dsh.profile`(列 bundles)/`dsh.bundle`(指向 patch 文件)。可用 `dsh --profile web --dump-config` 看实际合成。为什么:配置行(cordis.yml)+ 代码一起分发,层层可 patch → 第三方接管任意一层。来源:architecture.md。
- **Session log = 唯一真相**:"**Model-visible means logged.** Anything that reaches a model request must be reconstructable from the log, and a runtime invariant asserts it."(运行时断言,不只是约定)。`deriveMessages()` 从 log 投影模型历史;新增任何模型可见输入必须先扩展 `SessionEventMap` 加 session event。事件为 lossless JSON、`seq` 连续单调(含 `assistant/chunk` 原始流)。为什么:可回放/可审计/崩溃可恢复。来源:architecture.md、`docs/subsystems/session.md`。
- **turn/step 循环**:"A **step** is one model request plus the tools it calls. A **turn** is zero or more steps." 流程:`turn/start → agent/pre-step(可改写/拒绝将进入模型的消息)→ step/start → 从 log 派生历史 → agent/request → llm/stream → tool/call* →(tools/pre-execute→execute→post-execute)→ step/end → … → agent/turn-stopping → turn/end`。单一 inbox 驱动;注入的 context 在 inbox 等待、由别的消息唤醒。来源:architecture.md。
- **Capability seam 三角色**:"A capability seam comprises Service Definition / Service Provider / Consumer roles. It is complete, never one role"(AGENTS.md);"Extension plugins depend on Service Definitions, never concrete providers"(packages/README.md)。为什么:任意 provider 可换(如 shell 有 local/pwsh 两 provider、llm 有 DeepSeek providers)。
- **注册即效果(可逆)**:"**Registrations are effects**: every contribution goes through `ctx.effect()` / `ctx.on()`; a registry's `register()` returns the disposer."(AGENTS.md)。为什么:插件卸载 = 自动回滚全部贡献,支撑运行时自改。

## 关键 API·配置·扩展点(仅实际读到的)

- 扩展点(architecture.md 逐条):`ctx.llm`(model provider 适配器)· `ctx.tools`(模型可见工具,schema 进 prompt 装配)· `ctx.commands`(人类命令,"dispatches without a model turn")· `ctx.jobs`(后台工作,`job_*` 工具收集/停止)· `ctx.fs`(fs provider 或监听 `fs/*` 事件做策略)· `ctx.shell` / `ctx.terminals` / `ctx.sandbox`(执行后端)· `ctx.agents`(UI/编辑器集成,从 `session/event` 渲染)· `ctx.goals` · `ctx.sessionTitle` · `ctx.agentTeams`。事件钩子:`agent/pre-step`、`agent/request`、`agent/turn-stopping`、`fs/*`、`tools/*`、`telemetry/*`、`session/event`。
- Session 存储 API(`docs/subsystems/session.md`):`ctx.sessions` 拥有 "append-only `SessionEvent` log and in-memory store";方法 `create(id?, options?)` / `prepare` / `enter(session)` / `fork(source, boundary?, childSessionId?)` / `flush(session)`(awaited durability checkpoint)。事件字段:`type`/`seq`(`seq = log.length`)/`time`/`data` + 可选 `sourceEventSeqs`、`surfaceOp`。
- **Session 落盘**(`docs/subsystems/persistence.md`):抽象服务 `SessionPersistence` 在 `dsh-session-persistence` 包,两个后端实现:**`dsh-session-persistence-jsonl`**(默认,"an append-only logical JSONL log per session, stored as checksummed concatenated Zstandard frames by default or raw lines by configuration",路径为"project/session directory 内的 transcript 绝对路径")与 **`dsh-session-persistence-sqlite`**(opt-in,`node:sqlite`,schema 17,全部 session 共享一个 database)。崩溃恢复:发现只有 `turn/start` 没 `turn/end` 时**不截断**,补合成 `turn/end { reason: { kind: 'interrupted' } }`。版本:`SESSION_FORMAT_VERSION` 目前为 0、明言无兼容承诺(AGENTS.md "Pre-release stance")。具体 home 目录路径(如 `~/.dsh`)文档未写明——见"未查明"。
- Web ↔ server(`docs/api-gateway.md`):业务服务在 Host 上用 **`@Remote` / `@RemoteScope`** 装饰器选出暴露给 Client 的方法;构建生成 `typert.remote-client.js/.d.ts`;客户端经 `ctx.remote.<namespace>` / `agentCtx.remote.<namespace>` 调用;传输 = "`connection.rpc.call('/api', '<namespace>/<method>', { args }, signal)` … maps this to `POST /api/<namespace>/<method>`"。web 页面由 host 自带 webserver 提供(无独立 web server)。构建序:`build:lib:host → build:lib:client → build:web`(Typert 只在 Host 阶段跑,生成反射工件 + Host-for-Client 投影)。
- Python SDK(`python/README.md`,内容稀疏):`python/sdk`=**`deepseek-harness-sdk`**("high-level turns API and lower-level JSON-RPC client"),`python/sdk-runtime`=**`deepseek-harness-runtime-bin`**(打包的 runtime 二进制 + 默认 agent 配置);通信为 "newline-delimited JSON-RPC on stdio",SDK 把 dsh 作为**子进程**管理、自动启动匹配版本的 bundled runtime。另有 `packages/sdk/`(TS 侧 JSON-RPC protocol/server/client)与 `packages/acp/`(automation-only ACP server,`pnpm run demo:acp`)。AGENTS.md:"**Both SDKs project the loop**"——loop/`SessionEventMap` 变更须同步两个 SDK 的 expected outputs。
- 运行入口:`npx @deepseek-ai/dsh web`(Web UI 默认 `http://127.0.0.1:3080`)· `pnpm dsh --profile headless "task"` · `pnpm run demo:acp`。密钥:`DEEPSEEK_API_KEY` / 可选 `DEEPSEEK_BASE_URL`,或 repo 根 `.env`。
- cordis.yml 约定:`config` 与 entry `disabled` 下允许 `!!js`(禁 `!js`);条件装配走 overlay;bare plugin 必须出现在 resolver manifest 的 `dependencies`(`verify-cordis-config` 强制)。来源:AGENTS.md。

### monorepo 包地图(api.github.com/contents/packages 实测 53 目录;职责来自 AGENTS.md/packages/README.md)

- `core/`(session、system-prompt、tools、agent、agent-loop、scope——产品 API 脊柱)· `api/`(Remote BFF + Typert RPC gateway)· `typert/`(类型图生成/加载/运行时注册)· `llm/`(LLM capability + DeepSeek providers)· `boot/`(app-bin 胶水;profiles 机制在 `packages/boot/app-boot/README.md#profiles`)· `bundle/`(base/web-app/headless 等可安装 patch 层)
- 执行/文件:`shell` `subprocess` `terminal` `sandbox` `fs` `lsp` `code-runtime` `skill` `compaction` `e2b`(POC)
- 模型可见上下文与工具:`context` `subagent` `jobs` `workflow` `web`(搜索/抓取 provider+工具)`attachment` `spill` `todo` `plan`
- 装配/自改:`preset`(per-session 从 preset cordis.yml 合成 agent)`guard`(loop 卫生+工具超时)`extensions` `hooks`(Claude Code/Codex hook 桥)+ self-modification(AGENTS.md 列出;api 目录listing未单列,或已并组)
- 持久化/配置:`session`(持久化/投影/标题/遥测)`session-query` `storage` `settings` `credentials` `workspace` `identity` `goal` `schedule` `feedback`
- 集成/UI:`sdk`(JSON-RPC)`acp` `interaction`(审批/权限/ask-user)`host` `client`(浏览器侧包群,Client TS aggregate)`runtime-diagnostics`
- 支撑:`examples`(demo bundles:agent-spine + CLI/ACP/JSON-RPC bins)`experimental` `test-support` `util` `guard` — 另 `apps/` 仅 `cli` + `web` 两个应用壳。
- Host/Client 双 TS aggregate(`tsconfig.host.json`/`tsconfig.client.json`):因两侧对同一 cordis `Context` 接口做不同 declaration-merge,合成一个 program 会类型冲突——每包只属一侧,唯一例外 `api/remotes` 双面。来源:docs/development.md。

### examples/(嫁接姿势最直接的证据)

`examples/` = "runnable cordis.yml leaves over packages/examples bundles"——**只有 cordis.yml 接线 + demo 工件 + e2e/snapshot 场景,可复用逻辑一律抽回 packages/**(examples/AGENTS.md 原文)。六个例子:`acp-agent`、`headless-agent`、`jsonrpc-agent`、`mcp-memory`、`web-cordis`(agent 自改运行时)、`web-schedule`。每例配 keyless 测试(真 Loader 启动 cordis.yml 验证输出+干净退出)+ with-key 测试(验外部状态而非模型自述)。

## 设计哲学(原文 + 一句解读)

- "everything is a plugin"(repo description)——内核只是 Cordis 上下文,产品能力全部可拔插,agent 可自改自身运行时。
- "**Model-visible means logged.**"——上下文工程被强制成事件溯源:想给模型喂任何东西,先定义 durable event。
- "**Registrations are effects** … `register()` returns the disposer."——一切贡献可逆,插件生命周期=事务。
- "Extension plugins depend on Service Definitions, never concrete providers."——依赖倒置到极致,provider 可整体替换。
- "Explicit > implicit at package boundaries: defaulting is an explicit `resolve(request): Spec` step … never a hidden `?? default` inside `run()`."——默认值也是显式契约。
- "Trust TypeScript at typed same-process boundaries … validate at parser/config, queued, model/tool JSON, durable/file, worker, process, and wire boundaries."——校验只放在真边界,进程内信类型。
- "With no external consumers, prefer the correct foundation over compatibility shims"(pre-release stance)——preview 期一切格式可 breaking,`SESSION_FORMAT_VERSION=0` 无兼容承诺。

## 对"把一个 Python 领域系统(youzi)嫁接到 dsh 上"的启示

1. **官方姿势就是 Python-SDK-驱动子进程**:`deepseek-harness-sdk`(pip)以 stdio JSON-RPC 管理 bundled runtime,提供 "high-level turns API"。youzi 可保持纯 Python,把 dsh 当"会话运行时/LLM loop 外包件"调用——方向 A:Python 为主、dsh 为从,改动最小。
2. **反向嫁接(dsh 为主)则领域逻辑要过边界**:工具注册(`ctx.tools`)、扩展点全在 TS 侧;youzi 的决策/refine 逻辑要么经 MCP(有 `mcp` 包 + `mcp-memory` 例子)、要么经 subprocess 工具暴露给 dsh agent。examples/ 的铁律值得照抄:**接线归 cordis.yml,逻辑归包**——对应 youzi 现有 `youzi/`(领域)vs `youzi_web/`(壳)分层,风格同构。
3. **Session log 事件溯源 vs youzi 的 EditLog/SQLite**:dsh 把"模型可见⟺已记录"做成运行时断言;youzi 的对应物是 meta-tool 强制 + `_PATCH_FORBIDDEN`。若嫁接,youzi 的 `DecisionPackage`/refine 轨迹应映射为自定义 `SessionEventMap` 事件才能进 dsh 的回放/审计体系;但 `SESSION_FORMAT_VERSION=0` 意味着现在写的持久化格式随时被 breaking——**preview 期不要把 youzi 的真相源搬进 dsh session log**,保持 youzi/store 为真相、dsh 侧只做投影。
4. **Profile/bundle 分层 patch 很适合"H 即配置"的思路**:youzi 的 H(p,G,K,M)如果表达为一个 bundle + 上层 cordis.patch.yml,Refiner 的结构性编辑≈生成新 patch 层,且 dsh 的 disposer/可逆效果模型天然支持 rollback——与 `HarnessManager.checkpoint/rollback_to` 语义吻合,但这属于深度重构,preview 期风险高。
5. **审批/人确认**:`interaction/` 包(approval/permission/ask-user)是现成 seam,契合"人确认下单,绝不自动交易"的六道闸需求。
6. **现实约束**:Node 22.19+/pnpm/双 aggregate 构建链沉重;100% per-file 覆盖率门槛;文档明言随时 breaking。结论倾向:**短期用 Python SDK 或 ACP/JSON-RPC 做松耦合集成,别把 youzi 领域真相迁进 dsh**。

## 未查明/文档缺失(诚实清单)

- **session/settings 落盘的具体目录路径**(`~/.dsh`?"Harness home"具体在哪)——persistence.md 明确未写路径,只说 JSONL 在 "project/session directory"、SQLite 共享单库;需读 `packages/boot/app-boot/README.md#profiles` 或源码确认(未抓,URL:`https://raw.githubusercontent.com/deepseek-ai/deepseek-harness/master/packages/boot/app-boot/README.md`)。
- `apps/web/README.md` 404(apps/web 下结构未列);web app 由 host webserver 直接服务是 api-gateway.md 的推断性表述。
- Python SDK 的 turns API 具体签名/示例代码——python/README.md 内容稀疏,未抓 `python/sdk/README.md`、`python/development.md`(URL 已知,范围留给后续)。
- `packages/mcp/`、`packages/host/`、`packages/client/`、`packages/storage/` 的包内 README 未抓;`self-modification` 在 AGENTS.md 布局里但不在 api 目录listing中,存疑。
- 抓取模型对长文有压缩,除标注"原文引用"处外的措辞可能非逐字;architecture.md 全文未逐行核对。
- 未核对官方公告/博客(WebSearch 未动用);以上全部为 repo 一手材料。
- 范围外仅记 URL:`docs/cordis-primer.md`、`docs/testing.md`、`docs/glossary.md`、`docs/subsystems/README.md`、`docs/cookbook/adding-a-tool.md`、`examples/web-cordis/`、`native/README.md`(均在 `raw.githubusercontent.com/deepseek-ai/deepseek-harness/master/` 下)。