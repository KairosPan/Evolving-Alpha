## 核心概念

- **dsh(DeepSeek Harness)**:DeepSeek 开源的 agent harness,开发者预览版(明言持续 breaking changes)。核心命题 "Agent = Model + Harness"——harness 让模型"理解环境、用工具、在真实世界持续工作"。为什么:把模型能力与运行环境解耦,harness 本身成为可组合的产品。(https://deepseek.com/harness/en/ · README)
- **一切皆插件(Cordis)**:全部能力——模型、工具、技能、会话、沙箱、存储、循环、调度、UI——都是可换可重组的插件,插件系统叫 Cordis,设计源自一篇"spatiotemporal composability"论文。为什么:换任何一层(如换 LLM provider、换会话存储)不动其余层。(https://deepseek.com/harness/en/ · README)
- **Workspace(工作区)**:agent 可读写的目录;`dsh` 进程以启动目录为默认文件系统位置;Web UI 中必须先 "Choose workspace" 选定项目目录,**session composer(会话输入框)在选定 workspace 前不可用**。为什么:把 agent 的文件权限边界显式绑定到一个目录。(https://deepseek-harness.github.io/deepseek-harness/en/guide/quickstart)
- **Session(会话)**:append-only 会话日志,记录 system prompt、推理、工具调用与结果、子 agent 调度、每次 context 注入;SDK 侧复用 `session_id` 可保留 shell 状态与对话历史。为什么:可追溯 + 可恢复。(https://deepseek.com/harness/en/ · guide/python-sdk)
- **四个 runtime modes**(官方原文,https://deepseek.com/harness/en/):
  - **Standard**:"Full coding agent with file editing, shell, file and web search, skills, planning, goals, subagents, and workflows."
  - **Code**:"All Standard mode capabilities, with tools exposed through the Code Mode SDK so the model can combine multi-step operations in one TypeScript program."(用模型生成的 TS 程序编排多步工具调用)
  - **Minimal**:"Two-tool coding agent with persistent bash and str_replace_editor."(评测/消融用的受控环境)
  - **Creator**:"Built for creating custom agent presets, with all Standard mode capabilities plus runtime inspection, plugin experiments, and preset-authoring guidance."
- **权限体系 = sandbox mode × approval policy**:sandbox 有 `read-only`(fail-safe 默认)/`workspace-write`/`danger-full-access`;approval policy 有 `ask`/`never`;permission-presets 插件把二者打包成预设。Web UI "在活跃权限策略要求批准的操作前会先询问"。(reference/config-catalog · guide/quickstart · guide/python-sdk)

## 关键 API·配置·扩展点

- **启动**:`npx @deepseek-ai/dsh web`(或源码 `pnpm install && pnpm run build && pnpm dsh web`);Web UI 默认 `http://127.0.0.1:3080`,自动开浏览器,`--no-open` 关闭。(raw README master 分支;注意仓库默认分支是 `master` 不是 `main`)
- **配置文件**:`$DSH_HOME/.credentials.yaml`(API key,只写不显)+ `$DSH_HOME/settings.yaml`(凭据引用 + 模型设置)。(guide/providers)
- **Web UI 配模型**:Settings → Models → 填 DeepSeek API key → 保存即生效,无需重启。(guide/quickstart)
- **OpenAI 兼容自定义 provider**(guide/providers,route 级配置;经摘要模型转录,键名以下为实际读到的):

```yaml
llm-pi-ai:
  providers:
    <provider-id>:            # 永久 ID,进请求与会话
      apiKeyEnv: <ENV_VAR>
      api: openai-completions
      baseURL: https://<endpoint>/v1
      defaultInput: [text, image]   # 模型默认 text-only,vision 需显式开
      compat:
        supportsDeveloperRole: false      # 端点拒 developer role 时
        maxTokensField: max_tokens        # 从 max_completion_tokens 改回 max_tokens
models:
  - id: model-name
    input: [text, image]
    compat: { thinkingFormat: deepseek }
```

- **内置 DeepSeek provider 插件** `@deepseek-ai/dsh-llm-deepseek`(reference/config-catalog):`apiKeyEnv`(默认 `DEEPSEEK_API_KEY`)· `baseURL`(fallback `$DEEPSEEK_BASE_URL`)· `thinking: enabled|disabled` · `reasoningEffort: off|low|high|max`(默认 high)· `maxTokens`(默认 256000)· `defaultContextWindow`(默认 1000000)。默认模型经 `@deepseek-ai/dsh-agent-default-model` 的 `provider`/`model` 键指定。
- **工具呈现** `@deepseek-ai/dsh-agent-tool-presentation` 的 `mode`:`native`(逐工具 schema)/`code`(只发 `run_code` + 生成的 SDK)/`both`——即 Code Mode 的底层开关。(reference/config-catalog)
- **沙箱/审批**:`@deepseek-ai/dsh-sandbox-policy` 的 `mode`(默认 `read-only`);`@deepseek-ai/dsh-permission-presets` 预设结构 `sandbox: SandboxMode` + `approval: ApprovalPolicy`(策略含 `ask`/`never`)。(reference/config-catalog)
- **会话持久化两后端**:`dsh-session-persistence-jsonl`(`root` 必填、`packChunks` 默认 true、`compression: zstd|none`)/ `dsh-session-persistence-sqlite`(`path`、`journalMode: wal|delete|truncate|persist`、`busyTimeoutMs`)。(reference/config-catalog)
- **Python SDK**(guide/python-sdk):`pip install deepseek-harness-sdk`;运行时自带打包 Node,无需系统 Node.js:

```python
from deepseek_harness import DeepSeekHarness
with DeepSeekHarness(
    provider="deepseek-official", model="deepseek-v4-flash", max_tokens=49_152,
    cwd=str(workspace), session_root=str(sessions),
    cordis="examples/jsonrpc-agent/minimal.cordis.yml",
) as harness:
    result = harness.run("Inspect the repository and fix the failing tests.", session_id="example-001")
print(result.final_response)
```

  环境变量:`DEEPSEEK_API_KEY` · `DEEPSEEK_BASE_URL`(可指向自建 `/v1`)· `DSH_MODEL` · `DSH_SYSTEM_PROMPT`。SDK 例走 `danger-full-access`;工具仅 bash(300s 超时)+ str_replace_editor(输出 16000 字符上限);context compaction 关闭;会话为未压缩 JSONL。
- **示例目录**(https://api.github.com/repos/deepseek-ai/deepseek-harness/contents/examples):`acp-agent` / `headless-agent` / `jsonrpc-agent` / `mcp-memory` / `web-cordis` / `web-schedule`。`jsonrpc-agent/minimal.cordis.yml` 即 SDK 用的最小组合:JSONRpc server + deepseek llm + 持久 bash + editor + JSONL 持久化,显式关掉 skills/jobs/context 注入/compaction。
- **插件生态**:GitHub topic `dsh-plugin` 做社区插件发现。(README)

## 设计哲学

- "Every capability is a plugin that can be swapped or recomposed: models, tools, skills, sessions, sandboxes, storage, loops, scheduling, and the UI."——harness 不是框架而是插件总线,你的领域系统也应以插件身份接入而非 fork。(https://deepseek.com/harness/en/)
- 一切入 "append-only session log: system prompts, reasoning, tool calls and results, subagent scheduling, and every context injection"——审计优先,和本项目 EditLog 的思路同构。(同上)
- Minimal 模式官方定位是受控评测环境("Two-tool coding agent"),二手资料强调它"不是更差的 Standard 而是消融基线"——与本项目 `Hmin_*` 裸基线思想一致。(官方 deepseek.com;消融解读来自二手博客,需自行判断)
- 权限默认 fail-safe(`read-only`)、升权限显式(preset = sandbox × approval)——默认不信任 agent,与"人确认下单"哲学同向。(reference/config-catalog)

## 对"把一个 Python 领域系统嫁接到 dsh 上"的启示

1. **官方 Python 通道就是 `deepseek-harness-sdk`**:`DeepSeekHarness(cordis=<yml>, cwd=workspace, session_root=...)` 同步阻塞跑一轮,拿 `result.final_response`——youzi 的 `LLMAgentPolicy.decide()` 可以在保持 `DecisionPolicy` 协议不变的前提下,把"调 LLM"换成"调 harness.run"(harness 负责工具循环,youzi 负责喂 frozen 快照 + parse 输出)。
2. **cordis.yml 是组合点**:仿 `minimal.cordis.yml` 自定组合——关掉 web search 等触网工具即可维持"离线优先/未来函数防火墙"(agent 拿不到任意日期数据源,只给它 frozen MarketState 文件)。
3. **DeepSeek API 直配**:内置 `dsh-llm-deepseek` 用 `DEEPSEEK_API_KEY`/`DEEPSEEK_BASE_URL` 即可;任何 OpenAI 兼容网关走自定义 provider 的 `api: openai-completions` + `compat` 修正(`maxTokensField`、`supportsDeveloperRole`)。
4. **会话持久化后端可换 SQLite**——与 youzi/store 的"分域 SQLite 真相源"路线天然对齐;JSONL append-only 日志则可作为决策审计副本。
5. **权限模型可映射六道闸**:sandbox `read-only` + approval `ask` 正是"系统建议、人批准"的机器化表达;但注意 SDK 示例默认 `danger-full-access`,嫁接时必须显式换 preset。
6. Code Mode(模型写 TS 程序编排工具)对纯 Python 领域栈价值有限,除非把 youzi 能力包成工具后想让模型一次编排多步。

## 未查明/文档缺失(诚实列出)

- **runtime modes 的切换方式**(CLI flag?Web UI 开关?preset 名?)官方 guide/reference 均未写;四模式描述只在 deepseek.com/harness/en/ 营销页,"何时用哪个模式"的指引全来自二手博客(zimaspace/dshkit.dev 等,未核实)。
- **session composer** 仅一句"选 workspace 前不可用",字段/控件零文档。
- **权限批准的具体粒度**(哪些操作触发 ask、批准 UI 形态)未写;approval policy 是否有 `ask`/`never` 之外的值未确认。
- **dsh CLI 子命令**:除 `dsh web`(`--no-open`)外无任何 CLI 文档;guide 索引页(`/en/guide/`)404,可能还有未被链接的 guide 页。
- `llm-pi-ai` 这个 route 键名的含义/命名规则未解释;`$DSH_HOME` 默认路径未写。
- WebFetch 经摘要模型转录,以上 YAML 片段的字段名可信、缩进/完整性未逐字核验;`minimal.cordis.yml` 原文未拿到逐字版。
- 范围外仅记 URL:`/en/develop/basic/` · `/en/reference/cordis-primer` · `/en/reference/capability-seams` · `/en/reference/agent-lifecycle` · `/en/reference/tool-execution-pipeline` · `/en/reference/tool-catalog` · `/en/reference/persistence-catalog` · `/en/reference/cordis-api/{context,events,fiber,registry,service,inherited}`(均以 `https://deepseek-harness.github.io/deepseek-harness` 为前缀)。