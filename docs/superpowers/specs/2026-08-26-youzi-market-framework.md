# youzi-market:市场无关接入框架(replant 固定件第一刀)— 设计 v2

> 2026-08-26。v1 草案经三镜头对抗压力测试(crypto / 美股 / 防火墙-PIT,24 条发现含 10 设计级,全文 `docs/findings/2026-08-26-market-framework-stress.json`)修订而成。
> 定位:dsh 驾驶舱的第一个**固定**插件——只固定接入框架,不限定市场(cn-a / us / crypto 皆为模块)。桥 = 纯 Python MCP server(`dsh-mcp-client`,已实测通)。
> **⚠ 范围修正(2026-08-26 用户指示"不用加太多东西,留一个位置给 market 就行")**:v1 实际交付 = `youzi_mcp/{market_core,market}.py` 最薄实现——工具带 `market` 参数(默认 cn,其它值诚实报未接入)+ symbol 留 `cn:` 前缀槽位 + 真快照数据经 GuardedSource。**本 spec 的五不变量与 capability 契约降级为"第二个市场真要接入时的 checklist"**,届时按需兑现,现在不建多市场机器。v1 已顺手兑现的便宜项:输入校验前置(symbol 正则/market 枚举)、缺失三义(SnapshotMissingError 冒泡为显式 error、空 K 诚实空)、qfq ratio-only-safe 标注、handlers 纯函数+离线测试(tests/test_mcp_market.py,7 测试)。

## 1. 框架五不变量(压力测试后的修订版)

1. **可见性不变量(头号铁律的多市场形态)**:bar 合法 ⇔ `close_ts(bar) ≤ as_of`(tz-aware 时间戳比较,**不是日期标签比较**)。sessions 市场:日 d 的日线自该 session 收盘时点起可见(cn=15:00 CST;us 需感知 early-close/DST);continuous 市场按 bar 边界(crypto UTC 日 K 的 close_ts=次日 00:00Z)。**server 出口行级裁剪是第二道防线**:所有出工具面的帧按可见性规则截断,写成框架职责而非适配器自觉(现有 `GuardedSource.daily_ohlcv` 只查 `end` 参数、不做行过滤——live 轨必须补齐;`SnapshotSource` 已做行过滤可作参照)。
2. **as_of 游标所有权**:as_of 只能由**带外通道**设定——live 模式 = server 按市场 session 规则取 now;replay 模式 = `open_replay(start)→session` 由 server 持有游标、单调推进(对应 `AsOfGuard.advance` 的灵魂)。**MCP 工具面不存在任何能写 as_of 的入口**(模型自报 as_of = 防火墙自证明,禁止)。server 落 `(session, as_of, tool, params)` 访问日志——结构防御跨进程后,给出可事后机器审计的面。
3. **复权即事件(第二时间轴纪律)**:复权价有"知识时间"——fetch-time 锚定的复权因子(qfq/auto-adjust)把 as_of 之后的分红/拆股信息改写进历史价,**本身就是未来函数**。框架目标态:PIT 只存 raw + 公司行动事件表,读时按 `ex-date ≤ as_of` 现算;`adjust` 为框架自定义枚举、per-market 白名单,非法值 loud 拒,禁用"provider 默认"语义。**cn v1 现实**:沿用 qfq-as-of-capture 快照,显式标注 `ratio-only-safe`(现有消费面仅 scorer 取比值,复权基相消,经实读代码确认决策路径零 `daily_ohlcv` 调用——结构性遏制成立但属侥幸,禁止新消费方直接消费绝对价;禁止 us 模块复制此模式)。
4. **缺失三义分离**:① capability 未声明 → 工具不挂载/None;② 已声明但该日诚实无数据 → 显式状态(`NO_DATA`/`DELISTED(date)`/`HALTED`);③ 快照残缺/provider 故障 → **原样冒泡为 MCP error**(`SnapshotMissingError`/`PROVIDER_ERROR`),明文禁止洗成 None 或干净空帧(否则评测系统性剔除最坏尾部)。
5. **capability 契约 machine-readable**(`describe_market` 承载):`calendar_kind(sessions|continuous)` / `bar_tz` + bar 标签切法 / `volume_unit` / `adjust` 合法值及每值语义 / `backfillable: bool` + `lookback`(K 线可回补;深度/资金费率类错过即永失——两种 PIT 采集纪律)/ `symbol_stability`(cn 六位码终身不回收=stable;us ticker 会改名回收=alias 表;按 symbol 直落盘仅允许 stable 市场)/ provider 链 `mirror|distinct`(**只允许 mirror 型之间 fallback**——cn 三源是同一 tape 的镜像;crypto 各所独立撮合,跨所 fallback=静默换标的,必须 loud 失败)。

## 2. 工具面(MCP `youzi-market`,全部只读)

```
list_markets()                                  → [{market, provider_chain, capabilities, calendar_kind}]
describe_market(market)                         → §1.5 的全部契约,machine-readable
get_bars(symbol, start, end, freq, adjust)      → freq per-market 白名单(cn v1 仅 '1d'),白名单外 loud 拒
get_calendar(market, start, end)                → session open/close 时戳(不是纯日期)
market_snapshot(market, as_of_ts)               → 修订:参数从 day 改 as_of_ts("day"只是 sessions 投影,
                                                   cn 内部投影为交易日、工具语义不变;快照字段标 availability:
                                                   close-derived / live-capture-only,后者无 PIT 采集时诚实 None,
                                                   禁止历史日用实时端点回填)
# cn-a 挂载时追加(capability-gated)
cn_limit_pools(day) / cn_echelon(day)
```

- **输入校验前置**(模型可控输入首次直达路径拼接/akshare URL):`market ∈ 注册表枚举`;每市场声明 symbol 正则(cn: `^\d{6}$`),`<market>:<code>` 解析后不匹配一律拒——发生在进入任何适配器之前。
- v1 cn 的 `market_snapshot` 通用骨架字段(全市场涨跌家数/成交额)**不声明**(现有 6 方法协议推不出、akshare 相应端点多为仅当日实时):诚实缺失,待扩 capture 采集后自采集起始日才可得,新端点先过 `smoke_akshare.py` 核对列名。

## 3. 实现结构(离线可测是设计约束,不是事后补)

```
youzi_mcp/market/
  contract.py      # MarketModule 协议 + capability/错误模型(框架件,纯类型)
  guard.py         # 可见性裁剪 + as_of 游标(live/replay)+ 访问日志
  server.py        # MCP transport 壳(最薄:注册 handlers,零业务)
  handlers.py      # 工具处理器 = 对注入的 MarketModule 注册表的纯函数
  cn.py            # cn-a 模块:现有 AkshareSource/SnapshotSource/GuardedSource 薄适配
```

- **handlers 是纯函数**,transport 壳最薄;`tests/` 注册内存 `FakeMarketModule` 进程内直调 handlers(对齐 TestClient 模式)——**CI 零 live、零 dsh、零 MCP 进程**。
- `describe_market`/capabilities 为模块**静态元数据**,不实例化 provider;live provider 惰性构造且显式 opt-in,测试可断言 never-live。
- capture 侧框架校验(残 K 毒化防线):**丢弃 `close_ts > capture_ts` 的 bar**;manifest 记 per-series `last_complete_bar`,续跑从它开始(cn 收盘后抓的现有习惯零行为变化;crypto 无"收盘后"可依赖,此校验是必须品)。
- youzi 核心零改动:`MarketDataSource` 协议、495 测试原样;cn 遗留 snap 布局由 cn.py 直读不强迁。

## 4. 登记债务(不阻塞 v1)

- PIT per-market manifest(capture_ts/provider/adjust 语义/窗口)——与既有 D1 manifest 债务合流,us/crypto 模块启动时升 P0。
- us 模块:raw+事件表存储、实体键+symbol 别名表、盘前盘后声明;crypto 模块:exchange 进 symbol(`crypto:binance:BTC-USDT`)、weight/ban 限流模型、深度/funding 的 live-capture 采集器、ticker 重用断档告警。
- `GuardedSource.daily_ohlcv` 行级过滤缺失(source.py:192,live 轨)——框架出口裁剪已兜住工具面;youzi 核内消费方的同款加固登记为核心债务,不搭本件的车。
- 框架跨市场 ≠ 策略跨市场:《轮回》/oracle/fill 均为 A 股语义,不随框架泛化。

## 5. 验收(v1)

① 495 既有测试零触碰全绿;② 新增离线测试:可见性裁剪(含盘中 as_of 拒当日半根 bar)、as_of 无写入口、缺失三义各显式路径、symbol/market 校验拒注入、FakeMarketModule 全工具契约;③ dsh 侧手动验收:`mcp__youzi-market__*` 挂载、真快照数据出图、访问日志可查;④ `--dump-config` 产物入库。
