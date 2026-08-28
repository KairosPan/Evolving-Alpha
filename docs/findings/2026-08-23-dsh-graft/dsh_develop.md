# dsh 插件/扩展开发尽调笔记(Development 分区全爬 + 2 个 reference 子系统页)

来源根:`https://deepseek-harness.github.io/deepseek-harness/en/develop/`(下文简写 `DEV/`);reference 简写 `REF/` = `.../en/reference/`。共抓 11 页。文档为 developer preview,内容经摘要式抓取,引文以页面原文为准。

## 核心概念

- **Plugin(插件)**:一个 TypeScript 模块,导出 `name` + `apply(ctx, config)`;支持函数/对象/类三种形态。为什么:一切能力(工具、LLM 适配器、文件访问、agent loop 本身)都是插件,挂进共享 Context,系统即"插件树"。(`DEV/basic/`、`DEV/cordis-tutorial/`)
- **Cordis**:dsh 底层插件框架(`@deepseek-ai/cordis`,即 Koishi 系 cordis 的 fork)。提供 Context、服务注入、事件、生命周期。为什么:用一个小运行时统一"注册-清理-替换"语义,让任何能力可热插拔。
- **Fiber 生命周期状态机**:每个插件一个 Fiber,状态 `PENDING → LOADING → ACTIVE`(失败 `FAILED`)`→ UNLOADING → DISPOSED`。依赖(`inject`)未满足则停在 PENDING;服务消失时依赖方自动卸载、服务回来自动重载。为什么:依赖驱动的自动装卸是 HMR 与服务替换的前提。(`DEV/framework/`)
- **自动资源回收**:经 `ctx` 注册的一切(`ctx.on`、`ctx.tools.register`、timer)在卸载时自动清理;自定义资源用 `ctx.effect(() => disposer)`。Disposer 按注册逆序跑,异步 disposer 并发不保序。(`DEV/framework/`)
- **Service(服务)**:"a capability one plugin exposes to other plugins",按名字挂在 `ctx` 上(如 `ctx.tools`/`ctx.llm`/`ctx.agents`)。消费方声明 `inject: ['tools']` 保证就绪;可选依赖用 `ctx.get('name')`。(`DEV/framework/service`)
- **三角色能力设计**(官方 practice 模式):**Service Definition**(抽象类+类型契约,一个包)/ **Service Provider**(实现,可多个、cordis.yml 里选)/ **Consumer**(把能力包成 model-facing tool)。Provider 与 Consumer 只依赖 Definition,互不相识。例:`dsh-shell`(定义)← `dsh-bash-local`(提供)← `dsh-tool-bash`(消费)。(`DEV/practice/`)
- **Tool vs Skill(确切区别)**:
  - Tool = "A registered tool: its schema plus the execution function"——模型可调用的**执行**单元,注册进 `ctx.tools`(ToolRuntime),经 policy/guard 管道执行。(`REF/subsystems/tools`)
  - Skill = "optional instructions, not session events"——**可选指令文本**,存于 skill registry 而非会话历史;从文件系统发现(`<name>/SKILL.md` 或 `<name>.md`,kebab-case 命名,frontmatter 键 `disable-model-invocation`/`user-invocable`),由 model-facing 的 `skill` tool 按名取内容。即:tool 管执行,skill 管指令;skill 本身也是经一个 tool 暴露给模型的。(`REF/subsystems/skills`)
- **Bundle vs Profile**:Bundle = 带 `dsh.bundle.patch`(指向 `cordis.patch.yml`)的 npm 包,发行"一层配置";Profile = `$DSH_HOME/profiles/<name>` 下用户可运行组合,`dsh.profile.bundles` 有序列出各 bundle。为什么:配置即组合,分发与本地组装解耦。(`DEV/basic/publish`)

## 关键 API·配置·扩展点(仅列实读到的)

- 插件骨架:`export const name`;`export const inject = ['tools','llm']`;`export function apply(ctx: Context, config: Config)`。(`DEV/basic/`)
- `ctx.effect(() => cleanup)`(显式资源)· `ctx.plugin(child)`(嵌套子 Fiber,随父卸载)· `fiber.dispose()`。(`DEV/framework/`)
- **定义 tool**(`DEV/basic/tool`,`@deepseek-ai/dsh-tools`):
  ```ts
  ctx.tools.register(defineTool({
    name: 'greet', description: 'Greet someone by name.',
    parameters: { name: { type: 'string', required: true, description: '...' } },
    output: { schema: { type: 'string' }, render: (_args, v) => [{ type: 'text', text: v }] },
    async execute(args) { return `Hello, ${args.name}!` },
  }))
  ```
  `defineTool` 由 `parameters` 推断/校验 args,`output.render` 把 canonical 值转成模型可见内容。
- **ToolRuntime 公开方法**(`REF/subsystems/tools`,源码 `packages/core/tools/src/index.ts`):`register(def): ()=>void`(scoped 可遮蔽 global;同层重名与保留名 `run_code` 报错)· `execute(exec)`(经 pre-policy→guards→around-dispatch→post-policy→finalize→通知)· `schemas(scope?)`(**白名单**投影 model-facing 字段,"`output`/`execute`/... must never leak into a model request")· `get` · `guard(ToolGuard)` · `restrict(ToolRestriction)` · `presentAs(mode)`。`ToolDefinition` 另有 `finalizeContent?`/`timeoutMs?`/`isConcurrencySafe?()`/`presentCall?`/`presentResult?`。参数"cross one lossless-JSON materialization boundary ... and are deep-frozen"。
- **Tool 事件管道**(同页):`tools/change`(emit)· `tools/pre-execute`(waterfall,allow/deny/ask)· `tools/execute`(waterfall,包裹 dispatch 做超时/重试/metrics)· `tools/post-execute`(waterfall,接受/替换/拦截结果)· `tools/result`(emit,冻结终果)· `tools/code-dispatch-log`(waterfall)。
- **Skills 服务 `ctx.skills`**(`REF/subsystems/skills`,源码 `packages/skill/`):`registerProvider()` · `register()` · `list()` · `snapshot()` · `get(name)`;发现根按 rank:`.dsh/skills`(100)→`.agents/skills`(200)→custom(300)→`<dshHome>/skills`(400)→user-agents(500)→bundled(600);Config:`collectCacheMaxEntries?`/`customSkillDirs?`/`bundledSkillDir?`。四包分层:`dsh-skill`(定义)/`dsh-skill-filesystem`(provider)/`dsh-skill-badge`/`dsh-tool-skill`(consumer)。
- **提供服务**(`DEV/framework/service`):`class MetricsService extends Service { constructor(ctx){ super(ctx,'metrics') } }` + declaration merging `declare module '@deepseek-ai/cordis' { interface Context { metrics: MetricsService } }`;服务隔离:cordis.yml `isolate: { shell: true }` 让分组各持独立实例。
- **事件系统**(`DEV/framework/events`):`ctx.on`/`ctx.emit`;四种模式 emit(广播)/ bail(首个非空值短路)/ serial(注册序 await,首 truthy 停)/ waterfall(管道,**必须调 `next()`** 否则设计上即短路)。类型化:merge `interface Events`,命名约定 `namespace/action`。内建事件:`agent/step`、`agent/request`、`agent/request-error`、`tools/result`、`session/event`(其内含 `turn/*`、`step/*`、`tool/call`、`tool/result`、`compaction/*`)。
- **配置**(`DEV/basic/config`):导出同名 `Config` interface + Schemastery schema(`@deepseek-ai/schemastery`,`Schema.object({ greeting: Schema.string().default('Hello'), mode: Schema.union(['fast','accurate']).default('fast'), apiKey: Schema.string().required() })`);"Export schemas, not plain objects"(需 Standard Schema 接口);非法配置在**加载期**报错;改配置触发 HMR 式卸载重载。cordis.yml 条目:`- insert: [{ id, name: './src/x.ts', config: {...} }]`;条目字段还有 `id`(稳定身份供 HMR diff)与 `disabled: true`。(`DEV/cordis-tutorial/06-composition-and-hmr`)
- **LLM 适配器**(`DEV/practice/llm-adapter`):继承 `LlmAdapter` 实现 `stream()`(收 `GenerateOptions`,yield StreamChunk 序列:block-start → text-delta/tool-call-delta → block-end → usage → finish;"Every `block-start` has a matching `block-end`");`ctx.llm.registerAdapter(['provider-name'], adapter)`;可覆写 `resolveModel(provider, model, signal?)`、可选 `listModels()`;错误须抛带稳定 code 的 `LlmError`;"Every provider HTTP request must also merge `attributionHeaders()`" 且转发 `options.signal`。参考实现 `packages/llm/llm-deepseek/`(OpenAI 兼容)。cordis.yml 中 agent 选 provider/model:`@deepseek-ai/dsh-agent-loop` config `agents: [{ id: main, provider, model }]`。
- **打包/安装**(`DEV/basic/publish`):bundle package.json 带 `"dsh": { "bundle": { "patch": "./cordis.patch.yml" } }`;命令 `dsh plugin --profile demo add ./hello-plugin | github:you/repo | remove <pkg>`、`dsh --profile demo --dump-config`。**Patch 叠加顺序**:① profile 的 bundles 列表序 ② profile 自己的 cordis.patch.yml ③ `$DSH_HOME/cordis.patch.yml` ④ argv 序的 `--patch <path>`。GitHub 安装需 `prepare` 脚本 + pnpm 构建 allowlist。
- 开发起步:`pnpm dsh web --patch ./scratch-plugin/cordis.yml` → `http://127.0.0.1:3080`。(`DEV/basic/`、`DEV/basic/tool`)
- 诊断:遍历 `ctx.registry.values()` 的 fiber,`FiberState.PENDING` = 缺服务静默挂起。(`DEV/cordis-tutorial/06`)
- **可替换/可扩展的内建子系统**(reference 索引列出,页面本身未细读、仅记 URL `REF/subsystems/<x>`):session、session-query、persistence、session-title、llm-streaming、token-meter、system-prompt、tools、skills、workflow、storage、web-server、workspace、schedule。服务文档明言内建服务清单"generated into each service's subsystem page",不维护静态列表。

## 设计哲学(原文引用)

- "Cordis is the plugin framework underneath DeepSeek Harness: a small runtime where every capability — tools, LLM adapters, file access, the agent loop itself — is a plugin mounted into a shared context."(`DEV/cordis-tutorial/`)——没有"核心 vs 插件"之分,agent loop 也可换。
- "When a capability is general enough to need replaceable providers ... Harness separates three roles: a Service Definition, a Service Provider, and a Consumer."(`DEV/practice/`)——用类型契约而非实现耦合来解耦。
- "Avoid hardcoding tunable values ... Fail on invalid configuration"(`DEV/basic/config`)——配置即接口,错误左移到加载期。
- "Because unloading releases effects and loading follows dependencies, HMR can replace a running plugin by unloading and loading it."(`DEV/cordis-tutorial/06`)——HMR 不是特性,是生命周期语义的推论。
- Skills are "optional instructions, not session events"(`REF/subsystems/skills`)——知识注入与会话状态严格分离。
- schemas() 白名单:"must never leak into a model request"(`REF/subsystems/tools`)——模型可见面是显式投影,不是默认全量。

## 对"把一个 Python 领域系统嫁接到 dsh 上"的启示

1. **dsh 是 TypeScript/Node 单进程插件树**,Python 领域逻辑(youzi/)无法进程内挂载。可行嫁接面:(a) 写一个 TS Service Definition(如 `YouziService`)+ provider 经子进程/HTTP 调 Python(FastAPI 已有);(b) 把决策/复盘等操作包成 `defineTool` consumer 给模型调。三角色模式与本项目"协议(MarketDataSource/DecisionPolicy)+ 实现注入"高度同构,映射自然。
2. **tools 的 waterfall 管道(pre/post-execute、guard)是现成的"闸门"挂点**:未来函数防火墙、immutable-core 拒绝、人工确认(pre-execute 的 allow/deny/**ask**)都可实现为 policy 插件,不改工具本体——与"六道闸"理念同构。
3. **Harness 的 H=(p,G,K,M) 可部分映射**:K(技能库)→ dsh skills(SKILL.md 文件、registry、经 `skill` tool 取用);p(doctrine)→ system-prompt 子系统贡献;M → session/persistence 或自管 storage。但 dsh skill 是**静态指令文件**,没有本项目的 SkillStats/生命周期/信用回注——自进化编辑(meta-tools/EditLog)在 dsh 里无对应物,需自建(skills 服务支持 `registerProvider()`,可写一个由 SQLite 驱动的动态 skill provider,这是最顺的嫁接点)。
4. **LLM 适配层可复用**:`llm-deepseek` 参考实现即 OpenAI 兼容格式,与本项目 DeepSeek 栈一致;换模型只换 cordis.yml 的 provider/model。
5. **配置组合(bundle/profile/patch 叠序、isolate、disabled、HMR)**解决的正是本项目 compare_harnesses 的"多臂独立、杜绝交叉污染"问题:每臂一个 group + `isolate`,可借鉴其思想即便不迁移。
6. 成本警示:dsh 事件/服务语义(waterfall 的 next()、disposer 逆序、PENDING 静默挂起)都有隐坑;若只为 UI/编排而嫁接,收益需对比现有 FastAPI+HTMX 壳。

## 未查明/文档缺失

- **G(子 agent 群)/多 agent 编排**:`ctx.agents` 与 `agent/step` 等事件出现,但 Development 分区无 agents 专页;agent-loop 内部结构未读。
- **sessions/storage/workspace/schedule/web-server(UI)子系统详情**:仅有 URL(`REF/subsystems/...`),未抓页;UI 扩展(如何加面板/页面)在 Development 分区完全缺失(仅见外部示例 `github.com/deepseek-harness/turtle-ui`,未读)。
- **ToolGuard/ToolRestriction/ScopeKey 的具体类型签名**、`run_code` 机制细节:tools 页只给了方法级描述。
- Skill 的 `snapshot()`/badge provider 语义、skill 与 system-prompt 的注入路径细节。
- `dsh` CLI 全量行为、boot/cmdline:仅记 URL(repo `apps/cli/reference/README.md`、`packages/boot/cmdline/README.md`)。
- Cordis 教程 01–05 章正文未逐页抓(06/07 已抓,01–05 内容多与 framework 页重叠);`REF/cordis-primer` 未抓。
- 未做 WebSearch 补官方公告;以上全部为官方 docs site 一手内容,但经摘要式抓取,个别措辞可能为转述而非逐字。