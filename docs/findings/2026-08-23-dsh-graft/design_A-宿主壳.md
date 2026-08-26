# 嫁接设计:evolving-alpha × DeepSeek Harness — 立场 A【最小嫁接 · dsh 作宿主壳】

> 依据:8 路研究笔记(dsh 6 路 + proj 2 路)。凡引用 dsh 能力均标注笔记出处;笔记未覆盖的一律标 **[假设待验证]**。dsh 现为 developer preview(官方明示随时 breaking、`SESSION_FORMAT_VERSION=0` 无兼容承诺),本设计的总纲领因此是:**dsh 只当壳,真相不进壳**。

---

## 设计总览(一段话立场)

youzi 的 Python 领域核心——防火墙取数、评测尺、H=(p,G,K,M)、meta-tool/EditLog、信用回注、InnerLoop/compare——**一行不动**;dsh 只接管"外壳性"职责:操作员驾驶舱 UI、人机会话与 append-only 留痕、审批闸(人确认)、日程调度。嫁接面是一条**唯一的、极薄的进程间协议**:一个 TS 桥插件(`dsh-youzi-bridge`,项目中仅有的新 TS 代码,零业务逻辑)把 youzi 的窄命令 API 暴露为 dsh 工具,每次调用 spawn 一个短命 Python 子进程(`python -m youzi_bridge.cli`),stdin/stdout 走单次 JSON 信封。研究面(compare/smoke 脚本)完全不经 dsh。`youzi/store` SQLite 与 EditLog 仍是唯一真相源,dsh session log 只是观测投影——冲突时 store 赢。本设计诚实承认:它**放弃**了 dsh 的深层能力(Cordis 可逆效应治不了 Python 侧 rollback/_rebind 债、session 事件溯源不覆盖研究环、H 不做成 bundle-patch),换来的是六条硬不变量零妥协和随时可整体拔除 dsh 的回退自由。

## 组件映射表(youzi 现有构件 → dsh 概念)

| youzi 构件 | 处置 | dsh 对应物 | 理由 |
|---|---|---|---|
| `data/`+`replay/`(GuardedSource/AsOfGuard/PIT parquet) | **保留** | 无 | 头号铁律的载体,任何框架给不了(proj:code ②) |
| `universe/` `features/` `schemas/`(frozen 快照) | **保留** | 无 | 结构防御本体 |
| `eval/`(oracle/scorer/fill/stats) | **保留** | 无 | 领域客观尺 |
| `agent/`(LLMAgentPolicy/parse 幻觉过滤) | **保留** | 无(**不用** dsh 的 agent loop 做决策) | 决策路径必须留在防火墙内;dsh cockpit agent 只是操作员助手,不产生决策 |
| `refine/`(Refiner 4-pass/credit/signatures) | **保留** | 无 | 自进化核心;dsh skill 是静态指令文件,无 SkillStats/生命周期对应物(dsh:develop 启示 3) |
| `harness/`(H、metatools、EditLog、snapshot/manager) | **保留** | 无(EditLog 仅作只读投影进会话) | 观测/编辑边界与 immutable-core 全在此;rollback/_rebind 契约照旧 |
| `loop/inner_loop.py` `loop/compare.py` | **保留** | 无 | 熔断/水位线/防前视断言与调度骨架深度纠缠,拆分风险>收益(proj:code ①④) |
| `loop/run_store.py` | **按既定 spec 退役**(C 期迁 SQLite research 表) | 无 | 与嫁接正交;不搬进 dsh session log(dsh:repo 启示 3) |
| `youzi/store/`(SQLite 运营 7 表) | **保留,唯一真相源** | 不用 dsh storage domain | `SESSION_FORMAT_VERSION=0`、`domain/changed` 不跨进程(dsh:reference 风险) |
| `llm/client.py`+`cache.py` | **保留** | 不换 dsh-llm-deepseek | 决策/精炼 LLM 调用留在 Python(录放缓存=离线测试底座);cockpit 自己的模型才用 dsh 的 provider |
| `youzi_web/`(FastAPI+HTMX) | **三步退役**:并行→冻结只读→删除 | `dsh web` UI + 桥工具渲染(dsh:guide) | 嫁接的第一收益点;registry.Feature 外壳哲学由 cordis.yml 组合承接 |
| 原定 B-web 录入页(spec 2026-06-22) | **改道** | dsh 驾驶舱 + approval ask 承接录入 | 避免重复造 UI;spec 文档保留作回退方案 |
| `scripts/`(smoke/capture,手动触网) | **保留**;定时触发交给 dsh schedule | `schedule` 包/`web-schedule` 例/`ctx.jobs`(dsh:repo) | 调度器只按点触发幂等 CLI,逻辑仍在 Python |
| — (新增) | **新建** `youzi_bridge/`(Python CLI 适配层) | 桥的 Python 半边 | 与 youzi_web 同级:单向依赖 youzi,领域零感知 |
| — (新增) | **新建** `dsh-youzi-bridge`(TS 插件,<300 行) | `ctx.tools.register(defineTool(...))`(dsh:develop) | 官方文档没有 Python 写插件的路径(dsh:python-sdk 未查明清单),TS 薄桥不可避免——诚实承认这一层 |

## 运行时架构

```
 操作员(浏览器)
     │
┌────┴──────────────────────────────────────────────────────────┐
│ dsh web  http://127.0.0.1:3080   profile: youzi-cockpit       │
│  ├─ Web UI:会话 composer / 工具结果渲染 / 审批询问(dsh:guide)│
│  ├─ sessions:append-only JSONL 留痕,resume/fork(dsh:reference)│
│  ├─ 权限闸:permission-preset = sandbox×approval(dsh:guide)   │
│  ├─ cockpit agent(dsh-llm-deepseek;操作员助手,非决策者)      │
│  │    工具面 = 仅桥工具白名单;无 bash/fs/web-search           │
│  └─ dsh-youzi-bridge(TS 薄桥:拼参数→spawn→解析,零业务)      │
└──────────────────┬────────────────────────────────────────────┘
        每次调用 spawn:python -m youzi_bridge.cli
        stdin→ 单个 JSON 请求;stdout→ 单个 JSON 响应;进程退出
┌──────────────────┴────────────────────────────────────────────┐
│ youzi_bridge/(Python 适配层,单向依赖 youzi,无常驻进程)       │
│   窄命令白名单:market_brief/universe/decide/confirm_decision/ │
│   record_fill/positions/account/review_daily/refine_daily/...  │
│ ┌────────────────────────────────────────────────────────────┐ │
│ │ youzi/ 领域核心(原封不动)                                  │ │
│ │  akshare/PIT → GuardedSource → universe/features(frozen)   │ │
│ │  → LLMAgentPolicy.decide(H 渲染+DeepSeek+parse)→ eval      │ │
│ │  → apply_credit → Refiner(9 meta-tool→EditLog)→ InnerLoop │ │
│ │  store/SQLite=真相源 · harness snapshot · PIT parquet       │ │
│ └────────────────────────────────────────────────────────────┘ │
│ 研究面:scripts/smoke_compare 等纯 Python,不经 dsh             │
└────────────────────────────────────────────────────────────────┘
```

**数据流(驾驶舱日节奏)**:盘前——调度触发(或操作员一句话/命令)→ cockpit agent 调 `youzi_decide` 工具 → 桥 spawn Python → GuardedSource 固定 t=今日 → DecisionPackage JSON 返回 → 工具 `output.render` 在 UI 呈现排序候选+计划+理由(dsh:develop 的 defineTool render)。操作员逐条确认 → `youzi_confirm_decision` 工具触发 **approval ask** → 批准后写 store(领域 API 仍要求显式 human_confirm 载荷)。盘中/盘后——人在券商 App 手动成交后回填 `record_fill`;收盘 `review_daily` + `refine_daily`(触发 Python Refiner,编辑摘要作为工具结果留痕进会话)。整个交互全程落 dsh append-only session log,可 resume/fork 复看。**研究面数据流零变化**:compare_harnesses 照旧四臂 factory 隔离、直连 DeepSeek、产物落 store/研究表。

## dsh 买到了什么(逐条指认出处)

1. **驾驶舱 UI 免费得**:`npx @deepseek-ai/dsh web`、workspace 绑定、composer、审批询问界面(dsh:guide quickstart)。youzi_web 约二千行 FastAPI+HTMX 壳的功能与后续演进全部卸载。
2. **append-only 会话留痕 + resume/fork/replay**:"system prompts, reasoning, tool calls and results… every context injection" 全入日志,"Resume, fork, search, and replay all operate on the same event stream"(dsh:philosophy);`ctx.sessions.create/fork(boundary)/flush`、崩溃恢复合成 `turn/end{interrupted}`(dsh:reference)。人机确认过程从此天然可审计——这正是蓝图 §8"全程审计留痕"里我们准备自造的部分(proj:blueprint ⑤)。
3. **权限闸机器化**:sandbox `read-only` fail-safe 默认、permission-preset = sandbox×approval(`ask`/`never`)(dsh:guide config-catalog);tools `pre-execute` waterfall 的 allow/deny/**ask**(dsh:develop、dsh:reference);`interaction` 包(approval/permission/ask-user)(dsh:repo)。"人确认下单"的第二道防线不再自写。
4. **工具面即安全面**:`schemas()` 白名单投影("must never leak into a model request")、参数 deep-frozen、`timeoutMs`/`isConcurrencySafe`/`presentResult`(dsh:develop、dsh:reference)——桥工具的模型可见面是显式投影。
5. **组合即配置**:cordis.yml + profile/bundle/patch 叠序 + `disabled: true` + `dsh plugin --profile X add ./本地目录` + `--dump-config` 存档(dsh:develop publish、dsh:repo)——youzi-cockpit 剖面(去 bash/fs/web-search)用配置声明,不 fork dsh 源码。
6. **cockpit 模型直配 DeepSeek**:`@deepseek-ai/dsh-llm-deepseek`,`DEEPSEEK_API_KEY` env、凭证按请求时解析(dsh:guide、dsh:reference)。
7. **人类命令通道**:`ctx.commands` "dispatches without a model turn"(dsh:repo 架构文档)——/positions、/account 这类查询不必烧 LLM token。**[细节 API 未读,待 Wave 0 验证]**
8. **调度**:`schedule` 包 + `web-schedule` 示例 + `ctx.jobs`(dsh:repo 包地图)。**[假设待验证:schedule 的配置/API 全未读;证伪则退 cron/launchd 调 CLI,损失仅"调度进同一 UI"]**
9. **skills 作只读知识注入**:`.dsh/skills/<name>/SKILL.md`(rank 100 最优先)+ frontmatter 可调用性控制(dsh:develop、dsh:reference)——《轮回》playbook 的人类文档版给 cockpit agent 答疑用;**不放 H 本体**(H 渲染只发生在 Python 决策路径)。
10. **keyless 测试模式可借鉴**:真 Loader 启动 cordis.yml 验证输出+干净退出(dsh:repo examples)——TS 桥的独立测试 lane 照此办理。

**买不到/放弃的(诚实清单)**:Cordis 可逆效应与 reactive coeffects 不跨语言,Python 侧 `rollback_to→_rebind` 债照旧手工守;dsh session 事件溯源**不覆盖**研究环与决策 LLM 调用(它们在 Python 进程内;缓解:E1 缓存+store 已留全量请求/响应,桥在工具结果里带 decision_id/evidence 指针回链);isolate realms 不用于四臂隔离(Python factory 注入照旧);Code Mode、dsh storage domain、"H 即 bundle-patch"深嫁接(dsh:repo 启示 4)全部放弃——preview 期这些是负资产。

## 六条硬不变量逐条论证

**① 未来函数防火墙——守住,且 dsh 侧加了三道结构论证。** 决策路径 100% 在 Python 进程内,GuardedSource/frozen 快照/延迟打分一行未动。dsh 侧:(a) cockpit profile **不装** bash/fs/web-search——工具面只有桥命令白名单(cordis.yml 显式组合有据:minimal.cordis.yml 逐件声明、显式关功能,dsh:python-sdk/dsh:guide);(b) 桥工具 schema **不暴露 as-of 日期参数**——`youzi_decide` 内部固定 t=交易日历当日,复盘类命令只读 store 中已实现记录、不进任何决策推理路径;模型摸不到 execute 内部(schemas() 白名单 + deep-frozen,dsh:develop);(c) 存在"未来"的回放窗口(研究面)**完全不经 dsh**。验收手段:keyless 测试断言 cockpit 的 `ctx.tools.schemas()` 恰为白名单 **[测试写法待 Wave 0 验证]**。残余诚实项:防线部分依赖 profile 配置正确性——用 `--dump-config` 产物入库比对固化(有据)。

**② 观测 vs 编辑边界——守住,零迁移。** `_PATCH_FORBIDDEN`/`_UPDATE_FORBIDDEN`、apply_credit 直写、9 meta-tool 入 EditLog 全在 Python 原样。桥**不暴露任何 meta-tool 为 dsh 工具**;`refine_daily` 是"触发 Refiner 跑一遍"的粗粒度命令,编辑仍在 Python 拒绝管线内完成、入 EditLog 带 rationale;dsh session log 只记"触发了 refine + 编辑摘要"——这是观测投影,不是第二编辑入口。cockpit agent 无 fs 工具,物理上写不到 H。概念上 dsh 的 surface/log-only 二分与此边界同构(dsh:reference 启示 5),但本立场只借镜不迁移。

**③ immutable-core——守住,零变化。** `DoctrineEntry.__setattr__` 守卫 + `Doctrine.rewrite/remove` 双拦截全在 Python。dsh 层没有任何路径触到 doctrine 对象;唯一理论新风险是"有人给 cockpit 加 bash 改种子文件"——v1 不装 bash,若未来装,须 sandbox read-only 且 workspace 不含 seeds/(workspace 目录边界有据,dsh:guide)。

**④ 领域核心纯净——守住。** `youzi/` 零改动、零新依赖。新增 `youzi_bridge/` 是与 `youzi_web/` 同级的适配层(单向依赖 youzi);TS 桥在独立目录/仓,Python 侧对 dsh 零感知。架构测试延伸一条:断言 `youzi/*` 不 import `youzi_bridge`。宿主框架(dsh)被隔在两层进程边界之外,可整体替换——这恰是不变量④的原始意图。

**⑤ 离线优先——守住,但端到端有一个新盲区,诚实声明。** youzi CI 仍纯 Python 全离线:桥合同测试直接调 `youzi_bridge.cli` 的 main(JSON in/out;FakeSource/MockLLM 经 env 注入;DB 用临时文件/`:memory:`),golden 信封样例做双侧共享 fixtures。TS 桥零业务逻辑(拼参数→spawn→解析),单测 mock spawn + 可选 keyless loader 测试,放独立 lane,**dsh runtime 永不进 youzi CI**。诚实代价:「dsh web+桥+审批」的真端到端只能手动或独立 lane 验——这与今天"MockLLM 测不到 refine 实效"是同类已知盲区,且盲区只覆盖壳、不覆盖任何领域逻辑。

**⑥ 人确认下单、绝不自动交易——守住,三层独立防线。** 第一层(结构,与 dsh 无关):全系统**不存在任何券商接口**,"下单"物理上不可能——人只能在自己券商 App 手动下单后回填成交,嫁接不改变这一点。第二层(dsh):`confirm_decision`/`record_fill` 两个写命令配 approval **ask**(pre-execute waterfall ask 有据;**具体触发粒度与 UI 形态官方未写**,dsh:guide 未查明清单——Wave 0 实测,若 ask 无法精确到单工具则此层降级,不影响另两层)。第三层(领域):OpsRepository 命令 API 本身要求显式 human_confirm 载荷。三层各自独立成立,dsh 整个挂掉也不破此不变量。

## TS/Python 边界协议

**进程模型**:`dsh web`(Node,常驻)→ 桥插件(进程内 TS)→ **每次工具调用 spawn 一个短命 Python 子进程**,stdin 写一个 JSON 请求,stdout 读一个 JSON 响应,进程退出。无常驻 Python 服务、无端口、无 HTTP。选它的理由:最薄;状态全在 store/SQLite,天然无会话粘性;失败语义=干净的进程边界,不存在半死状态。冷启动约 0.5–1s,对日频节奏无感。(对照:官方 Python SDK 是反方向——Python 驱动 dsh 子进程走 stdio JSON-RPC(dsh:python-sdk);本立场驾驶舱面用不上它,列为 Wave 4 可选。)

**信封 v1**(唯一跨语言契约,版本化):

```
请求:  {"v":1, "cmd":"decide", "args":{...}, "trace_id":"..."}
成功:  {"v":1, "ok":true,  "data":{...}, "refs":{"decision_id":"...", "session_day":"..."}}
失败:  {"v":1, "ok":false, "error":{"code":"DUPLICATE_CONFIRM", "message":"...", "retryable":false}}
```

- cmd 白名单 v1:`market_brief / universe / decide / pending_decisions / confirm_decision / record_fill / positions / account / review_daily / refine_daily / research_summary`。大对象(DecisionPackage)整体内嵌 JSON;价格/金额传字符串定点。
- **失败语义三分**:exit 0 + `ok:false` = 领域拒绝(如重复确认、幂等冲突)→ 呈现给操作员;exit≠0 或 stdout 非 JSON = 基建故障 → TS 侧包装为工具错误(`tool/result` 的 `error` 字段有据,dsh:reference);超时由 `timeoutMs`(字段有据)兜底杀进程。写命令以 decision_id/fill_id 为幂等键,重放安全(record_fill 单事务原子化已在 main)。
- **并发**:写命令声明 `isConcurrencySafe()=false`(字段有据,**语义细节待验证**);SQLite WAL+busy_timeout 兜底;读命令并发自由。
- **谁调谁**:仅 dsh→Python 单向。信封由 youzi 侧定义并出 golden fixtures,TS 桥消费——dsh preview 的破坏性变更最多伤 TS 桥一层,信封与 Python 侧不动。

## 迁移波次

**Wave 0 — 侦察 spike(1–2 天,可整体丢弃)**。装 dsh,手写 hello 桥工具,逐项实测本设计的 [假设待验证]:approval ask 对自定义工具的粒度与 UI 形态;web-app profile 剥掉 bash/fs/web-search 后可用性;`dsh plugin add ./本地目录` 装载;schedule 包 API;session JSONL 落盘路径;`ctx.commands` 用法。产出=验证清单答案,不触 youzi 仓库。回退=删目录,零痕迹。**任何后续波次以 Wave 0 结论为门**。

**Wave 1 — 只读驾驶舱**。建 `youzi_bridge/`(只读命令)+ TS 桥只读工具 + `youzi-cockpit` profile(cordis.yml + preset);youzi_web 并行不动。离线可测:信封合同测试进 youzi CI(纯 Python,FakeSource/MockLLM/临时 DB);TS 单测+keyless 测试独立 lane。回退:不开 dsh,一切照旧——本波零风险。

**Wave 2 — 写路径 + 审批闸**。`confirm_decision`/`record_fill` 工具上线,approval ask preset 固化进 profile 并以 `--dump-config` 产物入库比对;**原定 B-web 录入页改道由驾驶舱承接**(spec 文档保留);youzi_web 冻结为只读备胎。离线可测:写命令合同测试(临时 DB,断言领域拒绝/幂等分支);审批层本身属壳盲区,手动验收单覆盖。回退:重启 B-web 录入页方案(spec 还在,成本=原计划)。

**Wave 3 — 调度 + 复盘会话化 + 退役**。盘前/盘后任务接 dsh schedule(Wave 0 证伪则退 cron/launchd 调 CLI,只损失"调度进同一 UI");每日复盘固定为 dsh session 模板(留痕、可 resume/fork 复看);EditLog 与研究结论经只读命令投影进会话;**youzi_web 删除**。离线可测:被调度的逻辑本体全是幂等 CLI 命令(纯 Python 可测),调度器只负责按点触发。回退:cron 触发 + store 数据完好,UI 损失可忍。

**Wave 4 — 可选,默认不做**。研究面观测增强:用 Python SDK(dsh:python-sdk)跑"复盘解说"会话,或把 CachedLLMClient 录放镜像转为 dsh 可浏览的 session 文件 **[假设待验证:UI 能否识别外部生成的 session;且 SESSION_FORMAT_VERSION=0 明言无兼容承诺——倾向永久搁置,研究面观测继续走 store/研究表]**。

## 风险与开放问题

1. **preview 破坏性变更**(官方明示;repo 建立仅 10 天)。对策已内建:真相源不进 dsh、信封由 youzi 定义、TS 桥是唯一受灾面且 <300 行、每波有回退路径。接受的残余风险:dsh 大改时驾驶舱短暂退回 youzi_web/CLI。
2. **approval ask 粒度未查明**(dsh:guide 未查明清单)——本设计第二防线的成色系于此;Wave 0 首要问题。降级不破不变量⑥(另两层独立)。
3. **schedule/commands API 全未读**(dsh:repo 仅见包名与示例名)——已按"证伪即退 cron"设计。
4. **TS 维护成本**:团队纯 Python 栈。对策:桥零业务逻辑、信封 fixtures 双侧共享、TS 变更只该发生在 dsh breaking 时。若 dsh 未来开放 Python 插件口(现状:官方零信息,dsh:python-sdk),桥可原地替换。
5. **双记与漂移**:dsh session log 与 store 复盘数据并存。裁决规则写死:**store 是唯一真相,dsh session 是观测投影**,任何冲突以 store 为准;禁止任何代码从 session log 读数据回流领域。
6. **cockpit agent 的言论风险**:操作员助手可能对候选做二次解读、被误当决策依据。对策:工具结果渲染中决策理由只呈现 DecisionPackage 原文(decision_id 可溯源到 store),preset 的 system prompt 明确其"呈现与操作,不改写建议"角色;dsh 的 system prompt 快照测试文化("插件不许偷加上下文",dsh:python-sdk)同向支持。
7. **开放问题**:中文 UI 支持程度(笔记无信息);TS 插件自 spawn 的子进程是否受 sandbox-policy 管辖(未查明——本设计不依赖它,防线在工具面而非沙箱);Wave 3 后单机单人假设是否维持(多用户不在本立场范围);北极星(HCH vs Hexpert 真实多窗对比)与本嫁接**完全解耦**——研究面不经 dsh,嫁接的任何波次都不阻塞也不污染北极星实验。