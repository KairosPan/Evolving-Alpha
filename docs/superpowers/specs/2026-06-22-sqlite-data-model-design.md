# SQLite 数据模型设计:从研究脚本演进为单机 Co-pilot 软件系统

> 日期:2026-06-22 · 分支 `phase-db-data-model` · 本文是 brainstorming 产出的设计冻结(spec),下一步交 `writing-plans`。
>
> 先读:`docs/findings/2026-06-09-arch-review.md`(D1 PIT 完整性债务)· `youzi/loop/run_store.py`(现 RunStore 文件存储)· `youzi/data/cache.py`(PITStore parquet)· `youzi/harness/{snapshot,edit_log}.py`(H 快照 + EditLog)· `youzi/eval/{decision,trajectory}.py`(Candidate/DecisionPackage/TrajectoryStep)· `CLAUDE.md` §不变量(防火墙/离线优先/分层)。
>
> 决策前置调研:本会话 `db-need-analysis` workflow(5 路并行通读持久化现状 + 三路线权衡),结论存于 memory `north-star-run-state`/项目 memory。

---

## 0. 一句话

把项目从"离线研究脚本 + 文件存储"演进为**单机本地单人 Co-pilot 软件系统**,新增一个 `youzi/store/` 包,用 **SQLite(标准库、单文件、离线可测)** 做持久化骨架。**分域真相源**:新增的运营/产品数据(全闭环交易日志)、研究/回测产物、Harness 演化史 → SQLite 当真相源;PIT 行情 → parquet 仍是真相、DB 只存 manifest 索引。访问层是**薄 Repository**(照抄现有 `RunStore`/`PITStore` 容器风格,手写 SQL,pydantic⇄行)。三条铁律(未来函数防火墙 / 离线优先 / 领域-web 分层)结构性守住;顺手闭合 D1(PIT 完整性)、`list()` O(N)、EditLog 二次写放大三个既有债务。

## 1. 已锁定决策(brainstorming,用户逐问确认)

1. **目标形态 = 单机本地单人产品** → SQLite,无认证/无多租户/无真并发需求。不上 Postgres,不上 ORM。
2. **覆盖范围 = 全部四域**:运营/产品数据(新核心)+ 研究/回测产物索引 + 活体 Harness 演化史 + PIT 行情快照。
3. **DB 角色 = 分域处理**:
   - 运营/产品 → **SQLite 当真相源**(全新,无现存文件,前向数据)。
   - 研究/回测产物 + Harness 演化史 → **SQLite 当真相源**(append-mostly 回放产物,风险低)。
   - PIT 行情 → **parquet 不动当真相源,DB 只存 manifest/索引**(PIT 不可变 + 整段重抓 + qfq 复权基准漂移 与 DB 行级 upsert 天性相悖;且是防火墙结构性防线)。
4. **运营闭环深度 = 全闭环**:决策 → 成交 → 盈亏(完整交易日志,你手工回填实际成交价/量,系统算实现盈亏)。
5. **访问层 = 薄 Repository + 标准库 `sqlite3`**:每域一个 `*Repository` 类,手写 SQL 映射 `pydantic ⇄ 行`,frozen 大对象整存 JSON `TEXT` blob 列,可查小元数据上列。

## 2. 不变量(改任何东西都要守)

1. **未来函数防火墙(头号铁律)**:
   - 决策路径(`DecisionPolicy.decide` / agent 构造)**永不持有 DB 句柄或 Repository**;只吃 frozen `MarketState`/`CandidateUniverse`(来自 `SnapshotSource → GuardedSource → parquet`,该路径一行不改)。
   - `pit_*` manifest 只被 `capture_window` / `snapshot_doctor` / web 读;**决策读价格路径碰不到 manifest**。
   - 运营数据天然前向(你自己 ≤t 的过往动作);研究/Harness 读出的是事后回放产物——**都不喂决策推理**。
   - 加架构测试:断言 agent/policy 构造签名够不到 DB 连接。
2. **离线优先**:`sqlite3` 标准库零新依赖;测试用 `Database(":memory:")`/tmp 库,永不触网;现有 466 测试继续全绿 + 新增 repo 测试同样离线。
3. **领域/web 分层(精确化)**:`youzi/store/` 在领域层。运营数据是 web 第一次"写"领域数据——干净解法是领域层暴露**窄命令 API**(`OpsRepository.confirm_decision(...)`/`record_fill(...)`),web 只调 API、不触领域内部。把"web 单向只读领域"精确化为"**web 经领域命令 API 读+写,不触领域内部**"。
4. **观测 vs 编辑边界**:`harness_edit` 表是 EditLog 的一等持久化,仍由 `metatools.py` 9 个 meta-tool 唯一写入;真实战绩(运营)若未来喂回 refine 必须走观测注入、**不入 EditLog**。
5. **PIT 不可变性**:parquet `一文件=一 as-of 帧`、整段原子重写语义不变;manifest 随 `put()` 事务写,可 `pit_reindex` 全扫重建,漂移时 **parquet 赢**。
6. **Crash-safety**:SQLite `WAL` + 单逻辑写一事务 = `os.replace` 同款"读者只见完整或旧态"保证。

## 3. 架构与模块布局

**新包 `youzi/store/`**(领域层),单库单文件,路径走 `YOUZI_DB`(默认 `./data/youzi.db`)。

```
youzi/store/
  db.py              # Database 连接壳:sqlite3 + WAL + foreign_keys=ON + 迁移 runner
  migrations/        # NNN_*.sql 按序幂等应用;schema_meta 表记 version
  ops_repo.py        # 运营全闭环 Repository + 盈亏结算服务(account.py 可拆)
  research_repo.py   # research_run / research_daily(替代/适配 RunStore)
  harness_repo.py    # harness_version / harness_edit(替代/适配 SnapshotStore)
  pit_manifest.py    # pit_root / pit_frame / pit_ohlcv manifest(parquet 不动)
  models.py          # 新增运营域 pydantic 模型(Session/Decision/Fill/Position/Review/...)
```

容器约定沿用现有风格:`__bool__ = True`、缺失值诚实 `None`(`pd.isna`/`is None`)、frozen 快照 `model_dump(mode="json")` 整存、向后兼容靠 pydantic `model_validator` 回填。

**血缘链**(把整库缝起来):
```
ops_session.harness_version  → harness_version → harness_edit   (今天的 H 怎么进化来的)
ops_session.decision_run_ref → research_run    → research_daily (今天的候选出自哪次跑分)
ops_candidate.pattern        → harness skill_id → 实战胜率 vs 回测 stats 对照
```

## 4. Schema(精确)

### 4.1 运营全闭环(7 表,SQLite 当真相源 —— 新核心)

```
ops_session ─1:N→ ops_candidate          (系统输出:排序候选 + 计划 + 理由)
     │
     ├──────1:N→ ops_decision            (你的动作:confirm/skip/manual_add/modify)
     │                │
     │                └─0/1→ ops_position
     ops_position ←N:1─ ops_fill ─N:1→ ops_decision   (实际成交,手工回填)
     │
     └─1:1→ ops_review(日级)   ops_position ─1:N→ ops_review(笔级)
ops_account_daily   (账户日快照 → 权益曲线)
```

| 表 | 关键列 | 角色 |
|---|---|---|
| **`ops_session`** | `session_id`★, `trade_date` UNIQUE, `regime_read`, `harness_version`(FK 软链), `decision_run_ref`(链 research_run), `no_trade_reason`, `note`, `created_at` | 一天一行;系统跑出当日输出的容器 |
| **`ops_candidate`** | `candidate_id`★, `session_id` FK, `code`, `name`, `pattern`(命中 skill_id), `rank`, `confidence`, `reason`, `plan_entry/plan_stop/plan_target`(可空), `plan_note`, `raw`(Candidate JSON), UNIQUE(session_id, code) | 系统**输出**的候选;映射 `Candidate`+`ScoredCandidate` |
| **`ops_decision`** | `decision_id`★, `session_id` FK, `candidate_id` FK(可空=手动加票), `code`, `action`(confirm/skip/manual_add/modify), `intent_side`(buy/sell), `planned_price/planned_qty`(可空), `status`(planned/executed/cancelled/expired), `note`, `created_at` | 你对候选/场外票的**决策** |
| **`ops_fill`** | `fill_id`★, `decision_id` FK(可空), `position_id` FK, `code`, `side`(buy/sell), `price`, `qty`, `filled_at`(T+1 语义关键), `fee`(可空), `note` | 实际**成交**,手工录(可分批多条) |
| **`ops_position`** | `position_id`★, `code`, `name`, `pattern`, `opened_on`, `closed_on`(可空), `status`(open/closed), `qty_open`, `avg_cost`, `realized_pnl`, `origin_decision_id` FK | 一个 code 一段持有 lot;由 fills 派生维护 |
| **`ops_review`** | `review_id`★, `session_id` FK(日级) 或 `position_id` FK(笔级), `body`, `tags`, `lesson_ref`(链 harness lesson_id), `created_at` | **复盘**;`lesson_ref` 是"复盘→记忆"的桥 |
| **`ops_account_daily`** | `trade_date`★, `equity`, `cash`, `market_value`, `realized_pnl_day`, `unrealized_pnl`, `note` | 账户日快照 → 权益曲线 |

**盈亏结算规则**(逻辑在 Python 域服务 `account.py`,不进 SQL trigger,保持可测):
- 买入 fill:`avg_cost = (avg_cost*qty_open + price*qty + fee) / (qty_open+qty)`;`qty_open += qty`。
- 卖出 fill:`realized_pnl += (price - avg_cost)*qty - fee`;`qty_open -= qty`;归零 → `status=closed`,`closed_on=filled_at.date()`。
- 缺失值诚实 `None`(没填计划价/费 → null,不臆造 0)。

**未来钩子(v1 schema 留好、不实现)**:`pattern` 贯穿候选/持仓 → 支持"按打法统计实战胜率";真实战绩可成自进化信用信号,但必须走观测边界(见不变量 4)。

### 4.2 研究/回测产物(2 表,SQLite 当真相源)

```
research_run ─1:N→ research_daily   (逐日逐臂投影,给 C5 跨 run 聚合)
```

| 表 | 关键列 | 设计要点 |
|---|---|---|
| **`research_run`** | `run_id`★, `start_date`, `end_date`, `scorer`, `horizon`, `temperature`, `ablate`, `created_at`, 北极星裁决上列:`hch_beats_hexpert`, `mean_excess`, `hit_rate`, `nuke_rate`, `statverdict_ci_low/ci_high/p/mde`, `report`(整个 `ComparisonReport` JSON blob) | meta + 裁决**上列可查**,`report` 整存。`list()` 只碰列、不碰 blob → **O(N) 全解析痛点消失** |
| **`research_daily`** | `run_id` FK, `arm`(HCH/Hexpert/Hcredit/Hmin_*), `trade_date`, `mean_score`, `mean_excess`, `hit`, `nuke`, `n_candidates`, UNIQUE(run_id, arm, trade_date) | 存盘时从同一 report 派生的逐日投影。**C5 一句 SQL `GROUP BY` 跨 run/跨窗算配对差** |

- `report` blob 是真相,`research_daily` 是同一次 `save()` 事务里派生的投影(可从 blob rebuild),单写路径不破。
- 保留 `export_run(run_id) → runs/<id>.json` 命令:研究产物仍能 `jq`/`git diff`/手 `cp`,把"DB 当真相"丢掉的可检视性补回。

### 4.3 Harness 演化史(2 表,SQLite 当真相源 —— 拆开 version 与 edit)

```
harness_version ─1:N→ harness_edit   (EditLog 升为一等行,终于可查)
```

| 表 | 关键列 | 设计要点 |
|---|---|---|
| **`harness_version`** | `version`★ INT, `label`, `kind`(live/research), `run_id`(可空,属哪次 compare), `created_at`, `harness`(整版 H JSON blob:doctrine+skills+memory+cycle) | 每 checkpoint 一行,仍整版快照供 rollback——**但不再内联 EditLog** → `O(版本数×log长度)` 二次写放大消失 |
| **`harness_edit`** | `edit_id`★, `version` FK, `seq`, `tool`, `target_kind`(skill/memory/doctrine), `target_id`, `op`, `summary`, `payload`(old→new JSON), `rationale` | `EditRecord` 拆成行。`by_tool`/`by_kind`/"第 N→M 版改了哪些 skill"变索引点查;**两套编辑历史撕裂消除**——web 审计面改读此表 |

- 保留策略:`harness_version.prune(keep_last=N, keep_referenced=True)` 解"只增不删"。
- rollback 语义不变:整版 `load(version)` + `_rebind`(旧引用债务照旧由 `_rebind`/factory 解,自写编排照做)。

### 4.4 PIT manifest(3 表,parquet 一行不动 —— 闭合 D1)

| 表 | 关键列 | 解掉的 D1 债务 |
|---|---|---|
| **`pit_root`** | `root_id`★, `path`(快照库目录), `label`, `calendar_start/end`, `created_at` | 多快照窗口登记,不再靠目录命名人工区分 |
| **`pit_frame`** | `root_id` FK, `kind`(zt/prev/blowup/dt), `trade_date`, `path`, **`state`**(present/empty_legit/empty_missing/out_of_range/error), `n_rows`, `col_fingerprint`, `fetched_at`, `source`(eastmoney/sina/tencent), UNIQUE(root_id, kind, trade_date) | **五态语义**:真无数据 vs 抓取失败空帧 vs blowup 超 30 日,不再混为一帧 → blowup_rate 系统性偏正消失 |
| **`pit_ohlcv`** | `root_id` FK, `code`, `path`, **`covers_start/covers_end`**, `state`, `n_rows`, `col_fingerprint`, `fetched_at`, `source`, UNIQUE(root_id, code) | **covers 范围**:旧 code 的 covers 不含新日期 → 该补抓,解"OHLCV 无窗口键";`col_fingerprint` 抓 akshare 列名漂移;`fetched_at` 兑现 as-of 承诺 |

- 谁读 manifest:`capture_window`(查 manifest 决定补抓,替代裸 `has()` 五态升级)、`snapshot_doctor`(新增强制门:扫到 `empty_missing`/列漂移就拒绝在脏快照上跑研究)、web/研究(完整性视图)。
- `SnapshotSource → GuardedSource → parquet` 读价格路径**一行不改、不碰 manifest** → 防火墙零新增侧信道。
- 同步规则:parquet 是真相,manifest 随每次 `put()` 事务写;可 `pit_reindex` 全扫 parquet 重建,漂移时 parquet 赢。

## 5. 分期实施(每期独立 spec→plan→实现→评审→FF 合并)

| 期 | 内容 | 价值 | 碰不变量? |
|---|---|---|---|
| **A** | `youzi/store/` 地基:`Database`(WAL+FK)+迁移 runner+`schema_meta`+`:memory:` 测试架 | 骨架 | 否 |
| **B** | **运营全闭环**:7 表 + `OpsRepository` + `account.py` 盈亏服务 + web 命令 API + 录入/复盘/权益页面 | **"软件系统"最大增量,独立,先做** | 仅分层精确化(不变量 3) |
| **C** | 研究迁移:`research_run/daily` + RunStore 适配/替换 + `export_run` + C5 聚合查询 + web 读侧改 | 解 list() O(N) + 北极星 C5 | 否(纯回放产物) |
| **D** | Harness 迁移:`version/edit` 拆表 + `SnapshotStore` 适配 + `prune` + web 审计改读 | 解二次写放大 + EditLog 可查 | 守观测/编辑边界(不变量 4) |
| **E** | PIT manifest:`pit_*` 表 + `PITStore` manifest 钩子 + capture 五态/covers 重写 + `snapshot_doctor` 强制门 + `pit_reindex` | 闭合 D1 | 守防火墙(不变量 1/5) |

**首份 writing-plans 聚焦 A+B**(地基 + 运营核心):最大产品价值、不碰任何现有不变量(仅分层精确化)、风险最低。C/D/E 各自随后,每期回到 brainstorm→spec→plan 循环。

## 6. 非目标(YAGNI)

- 不做多用户/认证/多租户/RBAC(单机单人)。
- 不做 Postgres/服务型 DB/连接池/真并发事务。
- 不做 ORM(SQLModel/SQLAlchemy/Alembic)——手写 SQL + 标准库迁移足够。
- 不把 PIT 价格行迁进 DB(parquet 当真相)。
- v1 不实现"真实战绩喂回 refine"(schema 留 `pattern`/`lesson_ref` 钩子,逻辑后续)。
- 不做实时行情/自动交易(项目铁律:绝不自动交易)。

## 7. 风险与权衡

- **派生投影一致性**(`research_daily` vs `report` blob):靠"单 `save()` 事务内从同一 report 派生"保证;可从 blob `rebuild`。
- **运营写路径对分层的精确化**:web 首次写领域数据,经窄命令 API 限制 blast radius;需架构测试守 agent/policy 够不到 DB。
- **DB 文件膨胀**:单人本地 GB 以下无虞;`harness_version.prune` + 运营数据天然有界。
- **迁移既有文件产物**:现 `runs/`(磁盘 0 个真实 run)与 `snap_*` 临时目录无历史包袱;C/D 期提供 `import_legacy` 一次性导入(若届时有文件)。
- **跨期软链**:`ops_session.harness_version`(目标表 D 期建)、`ops_session.decision_run_ref`(目标表 C 期建)在 B 期是**可空、不加 DB 级 FK 约束的软引用列**(存 version 号/run_id 字符串),仅当 C/D 落地后由应用层校验/联表。避免 B 期依赖尚未存在的表。

## 8. 测试策略

- 每个 Repository:`Database(":memory:")` 往返(写→读→pydantic 等价)、迁移幂等、向后兼容回填、缺失值 `None`、容器 `__bool__`。
- 运营盈亏:`account.py` 分批买入均价、卖出实现盈亏、归零平仓、缺费缺价的 None 路径——纯函数离线测。
- 防火墙架构测试:断言 agent/policy 构造无法获得 DB 连接;`SnapshotSource` 读路径不引用 manifest。
- 全程离线,永不触网;现有 466 测试保持全绿。
