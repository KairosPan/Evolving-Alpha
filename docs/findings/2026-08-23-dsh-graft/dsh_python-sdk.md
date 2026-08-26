# dsh Python 嫁接面尽调笔记(developer preview,repo 创建于 2026-08-13,默认分支 `master`)

**一句话结论:Python SDK 是"Python 客户端驱动 dsh 运行时"的形态——SDK 以子进程方式拉起捆绑的 dsh 运行时可执行文件,经 stdio 上的行分隔 JSON-RPC 2.0 与之通信;agent/工具/插件本体全部活在运行时(Node 侧、由 cordis 组合文件声明),Python 侧不是插件宿主。但协议是双向的(`next_request`/`respond` 存在),留有回程通道,只是文档未展示 Python 侧注册工具/技能/存储的官方路径。**

## 核心概念

- **DeepSeekHarness(高层 turns API)**:是什么——同步、可复用的门面类,`with DeepSeekHarness(...) as h: h.run(prompt, session_id=...)`,子进程生命周期归实例所有、跨多次调用复用。为什么——把"拉起运行时→initialize→跑一个 turn→收尾"压成一个上下文管理器,SDK 消费者不必碰 JSON-RPC。(来源:`python/sdk/src/deepseek_harness/api.py`;guide/python-sdk)
- **HarnessClient(底层 JSON-RPC 客户端)**:是什么——直接暴露 `request/notify/next_notification/subscribe_notifications/next_request/respond` 的泛用 RPC 客户端;README 明言 SDK 提供"high-level turns API and lower-level JSON-RPC client"两层。为什么——高层 API 只覆盖单 turn 编排,任何协议级扩展(自定义 method、事件订阅、回应运行时发来的请求)都下沉到这层。(来源:`client.py`;`python/README.md`)
- **runtime-bin(捆绑运行时)**:是什么——`deepseek-harness-runtime-bin` 平台轮子,内含编译好的 dsh 可执行"carrier"+默认 agent 配置;"The bundled runtime operates independently of system Node.js"(目标机不需要装 Node)。为什么——把 Node 运行时当作 Python 包的二进制依赖分发,`pip install` 即得完整 agent 栈;SDK "automatically launches the matching bundled runtime unless explicitly directed otherwise"。(来源:`python/README.md`;`python/sdk/pyproject.toml`;guide/python-sdk)
- **cordis 组合文件**:是什么——YAML(如 `minimal.cordis.yml`)逐件声明整台 agent 由哪些插件组成:`sdk-jsonrpc-server`、`llm-deepseek`、`sandbox`/`sandbox-policy`、`pty`/`terminal-bash`、`fs-local`、`agent-spine`、`persistent-bash`、`str-replace-editor`、`sessions`(JSONL 持久化)。为什么——repo 口号即 "Everything is a Plugin"(repo description),连"JSON-RPC 服务器面向 SDK"这件事本身也是一个插件(`sdk-jsonrpc-server`);Python 侧通过 `cordis=` 参数选择整台机器的形状。(来源:`examples/jsonrpc-agent/minimal.cordis.yml`;repo metadata)
- **Session 与 JSONL 持久化**:是什么——`session_root` 目录下按 `session_id` 落未压缩 JSONL;`h.start_session(session_id)` 返回轻量 `Session` 句柄(仅 `harness`+`id`+`run`)。为什么——会话状态归运行时管,Python 侧只持 id;复跑同 id 即续会话(推断自 API 形状,续跑语义未见文档明说)。(来源:`api.py`;guide/python-sdk)

## 关键 API·配置·扩展点(全部来自实际读取的源码/文档)

- `DeepSeekHarnessConfig` dataclass 字段(`api.py`):`provider="deepseek-official"` · `model="deepseek-v4-flash"` · `max_tokens` · `cwd`(工作区)· `runtime_cwd` · `session_root` · `cordis`(组合文件路径)· `env`(注:"runtime inherits the caller's environment by default")· `runtime_bin` · `launch_args_override` · `request_timeout_seconds` · `shutdown_timeout_seconds=1.0` · `base_url` · `api_key`。
- `DeepSeekHarness`(`api.py`):`__init__(config=None, **kwargs)` / `start()` / `close()` / `start_session(session_id=None) -> Session` / `run(input: str | list[JsonObject], *, session_id=None, on_notification: Callable[[Notification], None] | None) -> RunResult` / `client` property → `HarnessClient`。
- `RunResult`(`api.py`):`session_id` · `final_response` · `finish_reason` · `events: list[JsonObject]` · `notifications: list[Notification]` · `session_root`。模块级帮助函数:`normalize_input` / `final_response(events)` / `finish_reason(events)`(malformed 时 raise `SdkProtocolError`)。
- `HarnessClient`(`client.py`)出站 RPC:`initialize`(params `{cwd, provider, model, maxTokens?}`)· `session/prompt`(params `{sessionId, contentBlocks}`)· `shutdown`;泛用 `request(method, params, *, response_model: type[ModelT], timeout_seconds=None, on_notification=None, notification_filter=None, notification_subscription=None)`(响应用 pydantic model 校验)与 `notify(method, params)`。
- 入站(运行时→Python):事件/通知 method 名(源码中出现):`session.event` · `session.status` · `agent/inbox/spliced` · `assistant/message` · `turn/end` · `subagent.started` / `subagent.finished`(payload 带 `parentSessionId`/`childSessionId`)。订阅面:`next_notification()` · `subscribe_notifications(filter)` · `subscribe_session_notifications(session_id)`(经 subagent 生命周期边自动把**子孙 session 树**的事件并进来——`_session_parents` 映射 + `_notification_belongs_to_session_tree`)。
- **反向通道**:`next_request() -> IncomingRequest` · `respond(request_id, result)` · `respond_error(request_id, *, code, message, data=None)` ——运行时可以向 Python 侧发 JSON-RPC **请求**并等 Python 回应。用途未见文档示例(见"未查明")。
- 进程模型(`client.py`):`subprocess.Popen(stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True, bufsize=1)`;可执行解析顺序 `runtime_bin` → `bridge_bin` → 从 `deepseek_harness_runtime` 包 `resolve_bundled_launch_args`(缺则 `FileNotFoundError`);无显式配置时自动注入 `DSH_CORDIS_CONFIG`(指向 `bundled_default_config_path()`)。**纯同步 + 线程**:reader 线程解析 stdout JSON 行并路由到响应队列/订阅队列,stderr 线程留最近 400 行(超时诊断带 exit code + stderr tail);`threading.Lock` 保护状态、独立 `_write_lock` 串行化 stdin 写。**没有 asyncio API。**
- 环境变量(guide/python-sdk;example README):`DEEPSEEK_API_KEY` · `DEEPSEEK_BASE_URL`(OpenAI 兼容端点可自指)· `DSH_MODEL` · `DSH_SYSTEM_PROMPT` · `DSH_CWD` · `DSH_SESSION_ROOT`;开发者向:`DSH_RUNTIME_MODE=node`(用系统 Node 22.19+ 跑 built carrier)或 `launch_args_override` 直跑未编译 TS 源码(`python/development.md`)。
- 打包/成熟度(`python/sdk/pyproject.toml`;`python/development.md`):`name="deepseek-harness-sdk"`,**`version="0.0.0.dev0"`**,`requires-python>=3.10`,依赖仅 `pydantic>=2.12,<3` + `deepseek-harness-runtime-bin==0.0.0.dev0`(uv source 指向 `../sdk-runtime`,editable);hatchling 构建;"The root `package.json` version is authoritative for both Python distributions"(版本随 Node 主 repo 走);发布 = 1 个纯 SDK wheel + 3 个平台运行时 wheel,预发布版本按 PEP 440 归一。平台:Linux x64/arm64、macOS 14+ arm64;**PTY 后端要 POSIX 终端,明确不支持 Windows**。
- 示例(`examples/jsonrpc-agent/minimal.py` + README):无 UI——"stdout belongs to the SDK protocol and turns are driven by the SDK";full 变体给模型 `bash`/`read`/`write`/`edit`/`subagent`/`todo_write`,minimal 变体只给 persistent `bash` + `str_replace_editor`(300s 超时 / 16K 字符输出上限);示例策略是 `danger-full-access`,官方警告只在一次性环境跑。

## 设计哲学

- **"Everything is a Plugin."**(repo description)——运行时没有不可拆的核:LLM 提供方、沙箱、PTY、文件系统、会话持久化、乃至 SDK 服务器本身都是 cordis 里一行可换的插件。
- **"stdout belongs to the SDK protocol and turns are driven by the SDK."**(jsonrpc-agent README)——嵌入形态下 Python 是 turn 的**驱动者**,运行时是无头执行体;人机 UI 被整体拆除而非隐藏。
- **"The client selects the channel and supplies default configuration; the runtime itself always requires an explicit configuration."**(python/README.md)——配置无隐式兜底:SDK 负责挑运行时并递配置,运行时拒绝无配置启动;组合即真相。
- **"The runtime inherits the caller's environment by default."**(api.py)——务实的子进程模型:凭 env 传密钥/端点,SDK 不做密钥管理。
- 例外即失败的验收文化:"a plugin that contributes an unintended system section or user message fails the job."(development.md 快照测试)——system prompt 的每一段贡献都被快照锁死,插件不许偷加上下文。

## 对"把一个 Python 领域系统嫁接到 dsh 上"的启示(对 evolving-alpha)

1. **嫁接方向是确定的:Python 在上、dsh 在下。** youzi 的编排层(InnerLoop/compare)可以保留为 Python 主进程,把"一个 agent turn"外包给 dsh:`DeepSeekHarness(cordis=..., cwd=..., session_root=...)` + `run(prompt, session_id=day_id)`。这与现有 `LLMAgentPolicy.decide()` 的形状同构——dsh 相当于一个带工具/沙箱/会话的重型 LLM 调用。
2. **但工具/技能在运行时侧、用 TS 写(或用其自带插件)。** 想让 dsh 的 agent 直接调 youzi 的 `MarketDataSource`/meta-tool,官方路径是写 cordis 插件(Node 侧)——Python 侧没有文档化的工具注册 API。变通:a) 反向通道 `next_request`/`respond` 理论上可承载"运行时问、Python 答",但无文档背书,preview 期慎依赖;b) 让 dsh 的 bash/fs 工具跑 youzi CLI 脚本(最朴素、立即可用,但绕开了类型化协议,且要沙箱内可见 venv)。
3. **同步阻塞模型与 InnerLoop 的每日节奏天然合拍**;`on_notification` 流式事件 + `RunResult.events` 全量留痕可直接喂研究库落盘。subagent 树的事件自动归并(`subscribe_session_notifications`)对多臂/多子代理审计有现成支撑。
4. **不变量冲突要前置警惕**:示例组合是 `danger-full-access` + 继承全环境——与本项目"防火墙/离线优先"相抵,必须自写收紧的 cordis(sandbox-policy 换掉)并隔离 workspace;且 SDK 测试需真运行时二进制,"永不触网/纯离线测试"边界要重新设计(FakeHarness 替身)。
5. **成熟度风险**:`0.0.0.dev0`、repo 建立仅 10 天(2026-08-13→08-21 仍在 push)、版本随 Node 主 repo 浮动——API 面(尤其事件 method 名)应视为不稳定,嫁接层要做薄适配器隔离。

## 未查明/文档缺失(诚实清单)

- **Python 侧能否注册工具/技能/存储:未查明。** `next_request/respond/respond_error` 证明协议双向,但读到的文档/示例全部是"运行时自带插件 + Python 只驱动 turn";没有任何"Python-hosted tool/plugin"的官方 API 或示例。cordis 插件的实现语言文档未明说(捆绑在 Node carrier 内,强烈暗示 TS/JS)。
- `IncomingRequest` 的实际用途(权限请求?客户端工具?)——`models.py`(673B)与 `errors.py`(660B)未读,`SdkProtocolError` 之外的错误类型未确认。
- `session/prompt` 之外还有哪些运行时接受的 method(如 session 列表/恢复/中断);续会话(同 `session_id` 重跑)的确切语义未见文档。
- `python/sdk-runtime/` 目录内部、`python/sdk/tests/`(尤其 `next_request` 的测试用法)未读。
- cordis 文件的完整 schema、插件清单、`agent-spine` 的槽位模型——属别路范围,仅记 URL:`https://deepseek-harness.github.io/deepseek-harness/en/`(站点根)、`https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/python-sdk.md`(pyproject 里的权威文档链接)、`examples/jsonrpc-agent/cordis.yml`(full 变体)。
- 转写保真度注:本笔记引用的源码签名/YAML 结构经 WebFetch 中间模型转写,个别参数名可能有转写噪声;`0.0.0.dev0`、JSON-RPC method 名、进程模型等多处交叉印证过,置信度高。