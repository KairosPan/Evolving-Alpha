# DeepSeek Harness (dsh) 设计理念与 Cordis 内核理论 — 尽调笔记

来源基线:官网 https://deepseek.com/harness/en/ · 仓库 https://github.com/deepseek-ai/deepseek-harness · Cordis 论文《A Programming Paradigm for Spatiotemporal Composability》(Shi/Zhang/Cui, PKU+DeepSeek-AI, 2026-08-13 草稿, 88 页, https://github.com/cordiverse/paper)。dsh 为 **developer preview**(官方明示 "COMPATIBILITY-BREAKING CHANGES" 可能随时发生),文档确实稀疏,以下只写实际读到的。

## 核心概念

**1. Agent = Model + Harness;dsh = 插件化 harness**
- 是什么:dsh 把 harness 的一切能力做成 Cordis 插件:"models, tools, skills, sessions, sandboxes, storage, loops, scheduling, and the UI" 全部可换可组合;内核只负责 "plugin mounting, unmounting, and dependencies"。
- 为什么:让开发者 "select, swap, or extend any capability in configuration without changing the DeepSeek Harness source code"——能力扩展全部外置,内核零改(与本项目 `youzi_web/registry.Feature` append-only 外壳零改是同一哲学)。

**2. 时空可组合性(spatiotemporal composability)— 论文的中心命题**
- 是什么:动态组合的两个正交维度。**Temporal**(时间):卸载组件时,其对共享环境的全部副作用必须可完全回退。**Spatial**(空间):组件间依赖必须可声明、可被运行时反应式地解析/提供/撤回。
- 为什么:静态组合中二者退化为词法作用域与模块导入;动态场景(插件系统、**自进化 agent harness**)里现行做法只有"重启进程/容器编排"这种粗粒度替代,论文 §1.2.2 直指自进化 harness:没有 temporal composability,每次自我修改都要整体重启、丢光进程内状态,"a faulty self-modification can disable the very process needed to recover";没有 spatial composability,模块只能靠 ad hoc 手段感知依赖变化。

**3. 可逆效应(revertible effects)→ 时间维**
- 是什么:把效应建模为 `Γ → Γ × (Γ→Γ)`——作用于上下文并**同时返回自己的逆**。effect context `∂Γ := Γ × (Γ→Γ)`,第二分量是"累积器"(已发生效应之逆的复合);卸载组件 = 应用累积器(LIFO 回退)。逆的正确性(witness `g(δ)=γ`)是组件作者的义务,运行时只负责追踪与复合。
- 为什么:"a component's teardown is **derived from its loading** rather than written alongside it"——清理代码不再靠人写 deactivate 钩子(论文以 VSCode 为反例:activate 后无法运行时卸载,deactivate 只是关机回调)。等式只到**观测等价** ≃(如 free 不恢复堆布局)。跨组件乱序回退需效应两两独立(commutative key),否则顺序由累积器(组件内 LIFO)或声明的 coeffect(组件间)承担。

**4. 反应式余效应(reactive coeffects)→ 空间维 = 依赖注入的形式化**
- 是什么:把 IoC 容器形式化为 coeffect context `Σ = (k:K) ⇀ V_k`(带类型族的依赖表);组件声明依赖集 d,满足谓词 `σ ⊨ d`;每次上下文变更被分类为 **activating / deactivating / neutral**(notify),激活即执行组件效应(带追踪),失活即应用累积器回退。`set(k,v)` 本身就是效应函数——**coeffect 操作是 effect、effect 可逆**,两机制互为齿轮。
- 为什么:组件只在依赖齐备时激活、依赖消失时自动回退,"keeping them consistently wired as providers are added, removed, or replaced"——依赖重连不再是使用者的债务(对照本项目 rollback 后旧引用悬空、需手工 `_rebind` 的坑)。

**5. 统一上下文范式(context paradigm)**
- 是什么:`Γ∞ := μΓ. Γ × (Γ→Γ) × Σ`——递归自相似类型,把效应累积器与依赖表并入单一一等公民 ctx;组件与环境的**每一次交互都过 ctx**。effect 变换实现字面意义的 "plug-in" 隐喻:加载=执行效应(插入),卸载=回退效应(拔出),层级树上父 ctx 聚合子效应。
- 为什么(§3.3.3):函数式显式穿状态可追责但工效差,命令式隐式突变(React useEffect、Spring getBean)工效好但不可追责;ctx 范式两者兼得——"correctness that would otherwise rest on developer discipline becomes a **structural property of the paradigm**"。

**6. 组件/纤维/生命周期**
- 组件 = 三元组 `(d, p, e)`:依赖声明 d(inject)、供给声明 p(provide)、带逆的效应函数 e(apply)。**fiber** = 组件的一次实例化,携带自己的生命周期状态;registry 按名持有 fiber,父指针成树。coeffect 表是**派生的**:即活跃 fiber 供给的并集(提供者唯一)。
- 生命周期:基础二态 Inactive⇄Active;实现态机 `INACTIVE / LOADING / ACTIVE / UNLOADING / FAILED`,转移**有惯性**(inertia:一旦开始必跑完,再看 target 是否仍匹配,不匹配则链式进入下一转移);target 由依赖解析实时重算,依赖提供者换人(uid 变)即触发 reload。卸载顺序:提供者先停止供给(UNLOADING),等被通知的依赖方全部回到 INACTIVE 再执行自己的逆(排水式 teardown)。

**7. 隔离与拦截(fork/isolation 语义)**
- **coeffect isolation**:两层映射 `Σiso = (K⇀R) × ((r:R)⇀V_r)`——key 先经 realm 表 ρ 解析到 realm 再取值;`isolate(k,r)` 派生子 ctx 改写 ρ、共享表不动,故**无逆可追、丢弃派生 ctx 即恢复**(derived realization)。同一逻辑依赖在不同子树绑定不同值 = "runtime ad-hoc polymorphism",用于多租户、测试、组件沙箱。loader 层的 realm 分 local(私有随 entry 迁移)/ global(同名共享)。
- **coeffect interception**:`ι` 元数据表 + provider function,依赖被**访问**时合并 metadata(右偏,外层 ctx 可覆盖组件声明),"letting an enclosing context constrain how a component uses a coeffect without modifying that component"——运行时可装卸、不触发 reload。这是其能力式访问控制的机制(§6.3):inject 声明=capability 请求,ctx 代理=capability 仲裁,未声明访问直接抛错,orchestrator 可在加载前审计全部能力。

**8. 声明式装载器与 HMR**
- 配置 = entry 树(id/url/isolate/intercept/config/disabled),loader 做**增量 reconciliation**(按字段派最小扰动操作,keyed diff 递归);元定理保证终态只依赖最终配置、与操作顺序无关(quiescence)。HMR 把可逆效应用到模块级:dispose 旧 fiber 即回收全部效应,重导入后装新 fiber,**无需开发者标注 accept 边界**(对照 Webpack/Vite),失败则整体事务回滚。

**9. dsh 的可追溯性**
- "Everything the model sees is recorded in an **append-only session log**: system prompts, reasoning, tool calls and results, subagent scheduling, and every context injection." + "Resume, fork, search, and replay all operate on the **same event stream**." 单一事件流是恢复/分叉/检索/重放的共同底座。

## 关键 API·配置·扩展点(仅实际读到的)

**Cordis 核心库**(论文 §5.1 Table 2,https://github.com/cordiverse/paper → paper.pdf pp.54-61):
- `ctx.effect(callback)` — 唯一的上下文突变原语;callback 返回/yield 逆函数,返回 dispose 闭包(幂等,armed 标志),dispose 前缀复合进父 ctx 累积器(`∂²Γ` 递归)。
- `ctx.get(key)` / `ctx.set(key, value)` — 反射式 coeffect 读写;set 内部即 ctx.effect,自动追踪回收,装/卸均 notify 依赖方。
- `ctx[key]` — 属性式访问(TS 用 Proxy get trap);沿 fiber 链上溯,按 fiber.committed 视图解析并**强制 d 声明**:未声明→UNDECLARED_ACCESS,声明未激活→INACTIVE_ACCESS。
- `ctx.isolate(key, realm)` / `ctx.intercept(key, metadata)` — 派生子 ctx,见上。
- `ctx.use(component, config)` — 实例化组件为 fiber(注册即父 fiber 的一个被追踪效应,卸父级联卸子);`ctx.registry` 枚举 fiber。
- 组件接口:`component.inject`(依赖声明 d)、`provide`(供给 p)、`component.apply(ctx, config)`(效应函数 e);fiber 字段:`uid/inject/apply/ctx/parent/state/dispose/committed/target/inertia`。
- 内部符号槽:`ctx[@@store]` / `ctx[@@isolate]` / `ctx[@@intercept]`。
- Loader 组件:`@cordisjs/group`(子 entry 列表)、`@cordisjs/include`(外部 YAML/JSON 配置嫁接)、`@cordisjs/hmr`。
- 语言无关性注脚:`create_task` 显式写出以示语言无关——"with lazy scheduling (e.g., **Python coroutines**, Rust futures) the host must spawn the task for it to progress"(p.59 fn.2)。

**dsh**:
- 启动:`npx @deepseek-ai/dsh web` → Web UI 默认 `http://127.0.0.1:3080`(https://raw.githubusercontent.com/deepseek-ai/deepseek-harness/master/README.md)。
- 插件生态约定:插件仓库加 GitHub topic **`dsh-plugin`**(README;社区索引 https://github.com/topics/dsh-plugin)。
- Web UI 流:Settings→Models 存 DeepSeek API key;选 workspace 后 session composer 才可用;权限策略下先问再执行;agent 可读写 workspace 文件/跑命令/委派子任务/维护 plan(https://deepseek-harness.github.io/deepseek-harness/en/guide/quickstart)。
- **Python SDK**:包 `deepseek-harness-sdk`;`DeepSeekHarness(provider, model, max_tokens, cwd, session_root, cordis)` 上下文管理器 + `run(task, session_id)` → 结果对象含 `.final_response`;**页面只展示 Python 作为客户端,未展示 Python 写插件的路径**;传输协议未说明(https://deepseek-harness.github.io/deepseek-harness/en/guide/python-sdk)。

## 设计哲学(原文 + 一句解读)

- **"Everything is a plugin. Every run is traceable."**(官网)— 双支柱:空间上一切能力可插拔,时间上一切行为落在 append-only 事件流上可重放;恰好对应论文的 spatial/temporal 两维。
- **"Developers can select, swap, or extend any capability in configuration without changing the DeepSeek Harness source code."**(官网)— 扩展点在配置层不在源码层,内核是纯组合语义。
- **"correctness that would otherwise rest on developer discipline becomes a structural property of the paradigm."**(论文 §3.3.3)— 把"靠纪律守"的清理与依赖重连,变成运行时的结构保证——与本项目"不变量靠评审守"形成鲜明对照。
- **"a component's teardown is derived from its loading rather than written alongside it"**(论文 §3.3.3)— 逆随效应给出,卸载免费。
- **"a plugin whose dependency is unavailable stays inactive until it appears, without erroring"**(论文 §5.3 Koishi)— 依赖缺失是常态而非异常;4000+ 社区插件生态即其压力测试。
- **"unlike application frameworks that target a specific domain…it prescribes no concrete scenario; its sole responsibility is to supply universal dynamic composition semantics"**(论文 §5,meta-framework 定位)— Cordis 不带领域词汇,dsh 只是其上的 agent 领域词汇包(Koishi 是聊天机器人词汇包)。

## 对"把一个 Python 领域系统嫁接到 dsh 上"的启示

1. **官方 Python 路径今天只有客户端**:`deepseek-harness-sdk` 是驱动 dsh 会话的薄包装,`youzi/` 若接入,现实形态是 "Python 域系统 = orchestrator,dsh = 被调的 agent 执行器",而非把 youzi 逻辑做成 dsh 插件。想成为一等插件得写 TS(或等官方开 Python 插件口)。
2. **跨进程是论文钦定的桥**:§6.2 服务代理(service broker)+ RPC 做 cross-process invocation,"An interface intended to be exposed across processes must therefore be designed against an **asynchronous contract**"——若把 youzi 域逻辑封成 dsh 可注入的远程服务,接口必须异步化。
3. **范式本身语言无关,Python 被点名可行**:§6.4 明说空间维在运行时层需要透明访问拦截,"e.g., via JavaScript's Proxy object or **Python's descriptor protocol (`__get__`)**";时间维只需闭包+可撤模块注册。理论上可在 Python 内自建 mini-Cordis,但官方没有实现——这是自研成本而非拿来即用。
4. **理论与本项目痛点强共振**(嫁接的真正价值在借理念,未必在借运行时):
   - `HarnessManager.checkpoint/rollback` 是**快照式**回滚;Cordis 是**构造式**回滚(逆随效应累积)。后者天然解决本项目 "rollback 后旧引用悬空需 _rebind" 的债务——reactive coeffects 会自动 deactivate/reactivate 依赖方。
   - 9 个 meta-tool 全走 EditLog ↔ Cordis "每次突变必过 ctx.effect 单一原语";观测 vs 结构编辑边界 ↔ 效应(可逆、入账)vs 派生 ctx(isolate/intercept,不入账、丢弃即恢复)的两分。
   - compare_harnesses 的 factory 注入防交叉污染 ↔ **isolation realms** 就是为"同 key 不同臂不同绑定"造的机制(多租户/测试/沙箱)。
   - 每日 refine 编辑活体 H = 论文 §1.2.2 的自进化动机原型;声明式配置 + keyed-diff reconciliation 与"种子 H + 每日 CRUD"同构。
5. **风险**:developer preview、明示会破坏兼容;内核 TS 与 youzi 纯 Python 栈异构,引入 = 增加一整个运行时;论文自认证据是"existence-and-adoption result rather than a quantitative one"(单生态单语言,无对照)。

## 未查明/文档缺失(诚实清单)

- **Runtime modes 全貌未查明**:官网有 "Runtime Modes Overview" 一节,但首页/README/quickstart 实际只写清了 Web UI 一种(`dsh web`);quickstart 提 "其他 CLI modes" 而未列名。待查:https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/README.md
- **dsh 插件开发 API**(插件如何注册 model/tool/skill、config schema)未读,范围外只记 URL:https://deepseek-harness.github.io/deepseek-harness/en/develop/basic/ · https://github.com/deepseek-ai/deepseek-harness/blob/master/AGENTS.md · /en/guide/providers
- **Python SDK 传输协议未说明**(进程内 or 子进程 or HTTP 不明);Python 写插件是否可能,官方文档零信息。
- **Cordis 实际 TS 仓库未读**(https://github.com/cordiverse/cordis):论文呈现的是 Cordis **v4** 语义,Koishi 现用 **v3**(论文 fn.4),dsh vendored 的版本号未查明——纸面 API 与实仓可能有出入。
- **session log 的事件 schema/存储格式**、六项官网未提的细节(sandbox 实现、权限策略模型)未查明。
- 背景数据为**二手**:v0.1 preview 2026-08-13 发布、MIT、"两天 95k stars" 来自 MarkTechPost/Flowtivity 等第三方报道,非官方口径。
- 论文为 **preprint under active revision**("content may change substantially"),引用需注日期(Draft of August 13, 2026)。

Sources: [deepseek.com/harness/en/](https://deepseek.com/harness/en/) · [cordiverse/paper](https://github.com/cordiverse/paper)(paper.pdf 本地副本:/private/tmp/claude-501/-Users-pan-Desktop-self-evolve-evolving-alpha/c40186b2-297c-4f8b-940b-6f217451ca03/scratchpad/cordis-paper.pdf)· [deepseek-harness README](https://github.com/deepseek-ai/deepseek-harness) · [quickstart](https://deepseek-harness.github.io/deepseek-harness/en/guide/quickstart) · [python-sdk](https://deepseek-harness.github.io/deepseek-harness/en/guide/python-sdk) · 二手:[MarkTechPost](https://www.marktechpost.com/2026/08/17/deepseek-ai-releases-deepseek-harness-in-developer-preview/) · [Flowtivity](https://flowtivity.ai/blog/deepseek-harness-open-source-agent-explained/)