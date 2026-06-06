# Findings:首次真实数据自进化对比 —— HCH 持续退化于 frozen(论文 §6.9 复现)

> 日期:2026-06-06 · 数据:真实 akshare(A股)+ 真实 DeepSeek(`deepseek-chat`,temperature=0.3)· 工具:`scripts/smoke_compare.py`(`compare_harnesses`)
>
> **一句话**:系统第一次在真实数据上端到端自进化,**三个独立窗口一致显示 HCH(每日自精炼)跑输 Hexpert(冻结种子 H)**。这是论文《Continual Harness》§6.9 最重要的负面发现(bootstrap 自更新可退化到比 frozen 还差)在 A 股真实数据上的复现。introspection 看清了退化机制。

---

## 1. 实验设置

- `compare_harnesses` 四路同 source/区间/horizon=1/同 oracle(池成员制 continued/faded/nuked):
  - **HCH** = `InnerLoop` 自精炼内环(每日 act→延迟打分→在线信用→能力地板熔断→每日 refine,真实 DeepSeek 既驱动 agent 又驱动 Refiner)。
  - **Hexpert** = 冻结种子 H + 同款 agent,**无 Refiner**(H 全程不变)。
  - **Hmin_highest** = 无脑追最高连板;**Hmin_notrade** = 永远空仓。
- 每路独立 fresh 种子 H + 独立 DeepSeek client(`_MemoizedSource` 让四路共享完全相同的真实行情,公平性硬保证)。
- 三个窗口(均在 akshare 池数据可取的最近 ~30 交易日内):`2026-05-12~19`、`05-20~28`、`05-29~06-05`。

## 2. 结果:3/3 窗 HCH < Hexpert

| 窗口 | HCH exp | Hexpert exp | Δexp | HCH 命中率 | Hexpert 命中率 | HCH 被砸率 | Hexpert 被砸率 | verdict | HCH refine |
|---|---|---|---|---|---|---|---|---|---|
| 05-12~19 | +0.333 | +0.500 | **−0.167** | 0.667 | 0.750 | 0.333 | 0.250 | ❌ | 1 |
| 05-20~28 | +0.188 | +0.211 | **−0.023** | 0.312 | 0.368 | 0.125 | 0.158 | ❌ | 5 |
| 05-29~06-05 | +0.050 | +0.267 | **−0.217** | 0.250 | 0.333 | 0.200 | 0.067 | ❌ | 4 |

- **方向 3/3 一致**:HCH 期望分始终低于 Hexpert(Δ −0.02 ~ −0.22)。
- **样本小**(每窗 3~20 候选),**magnitude 是噪声量级,但方向一致性已超出单窗噪声**。
- 参考:Hmin_highest 在个别窗口(05-12~19 的 +1.0、单候选)因小样本偶然居首——同样别过度解读。

## 3. 退化机制(由 `hch_loop_report` introspection 看清)

读 HCH 每次 refine 的 applied 编辑(`smoke_compare` 现会打印),病因清晰:**Refiner 在极小样本上过度收缩(over-restriction)**。

1. **几乎每次 refine 都在"砍"**:基于 1-2 次 `faded` 就 `patch_skill` 加禁忌 / `retire_skill` 退役。例:
   - 05-20~28 到第 4 次 refine 已退役 `w2s_strong_stronger`、`relay_1to2`、`kht_emo_extreme_open_first_board` 三个核心技能 → HCH 后段可用工具锐减、越来越胆小 → 错过 Hexpert(满技能)抓到的 continued 赢家。
   - rationale 原话:"relay_2to3_w2s n=2 胜率0.00 … 暂时退休"、"w2s_weak_to_strong n=2 胜率0.00 … 退休"。
2. **把 `faded`(空耗,SCORE 0)当亏损(−1)惩罚**:faded 只是"没续上"、非真亏,但 Refiner 拿它当强证据退役/收紧 → 过度规避 → 漏掉 continued。
3. **n=2/n=4 就做结构性编辑**:典型小样本过拟合噪声;Refiner **无"结构性编辑最小样本门槛"**。
4. **能力地板熔断 3 窗全程未触发**:HCH 期望分始终 >0(只是 < Hexpert),自相对地板/绝对地板都没破 → **自相对地板抓不到"比 frozen 差"**。

## 4. 真实 DeepSeek 暴露的 meta-tool / 提示摩擦(被 rejected 的编辑)

- `update_memory(..., regime="…")` → `ValidationError: Lesson Object has no attribute 'regime'`:LLM 很自然想更新教训的 regime,但 `Lesson` 的 regime 只在 `from_seed` 创建时解析,`update_memory` 直接 setattr `regime` 不被允许。
- `update_memory` 漏 `lesson_id` → `KeyError: 'lesson_id'`(LLM 偶尔不带 id)。
- `process_memory` 跨 refine **重复同一 lesson_id** → 多次 `重复 lesson_id` 拒绝(提示未显式列出已有记忆,LLM 重复提同一条新教训)。

这些不影响正确性(拒绝管线如实挡下、不半应用),但浪费编辑额度、降低自精炼效率。

## 5. 价值与结论

- **正面**:论文两环自进化在 A 股真实数据上**第一次完整转起来**——真实取数→agent(live H)选股→oracle 打分→在线信用→真实 DeepSeek Refiner 改 H→次日生效,全程不崩、防火墙守住、对比机器输出可信。
- **关键结论**:**当前朴素的"每日 refine + 小样本即编辑"会让系统退化到比 frozen 还差**——这是预期中的、有价值的负面结果,恰恰证明能力地板/纪律机制不是可选项而是必需。
- **不是 tradeable 结论**:无成本/滑点、horizon=1 单日池成员 oracle、单次 LLM 采样、小样本;只说明"机制需要纪律",不说明"打法本身好坏"。

## 6. 由本结果驱动的行动方向(优先级)

1. **Refiner 纪律化(治本,最高优先)**:
   - 结构性编辑(`retire_skill`/加禁忌)加**最小样本门槛**(如 n≥K 才允许退役);
   - **`faded` 权重 < `nuked`**(faded=漏、nuked=亏,不应同等触发收缩);
   - 提示里**列出已有记忆**(避免重复 lesson_id)+ 修 `update_memory` 的 regime/lesson_id 摩擦(或提供"更新 regime"的合法路径)。
2. **1b-3c 影子 Hexpert 严格地板**(安全网):环内并行跑冻结 agent,HCH 滚动跌破 Hexpert margin 即熔断冻结——自相对地板抓不到的"比 frozen 差",影子地板能抓。
3. **多窗口/多 episode 聚合 + 统计显著性**:当前 3 窗是定性方向,需更多窗口 + 跨 regime 才能下定量结论(1b-3b 债务)。
4. **P0 `_RENAME`**:dt 池 `封单资金→seal_amount`(本对比不受影响,但补全)。

## 7. 复现命令

```bash
# 单窗口(需 DEEPSEEK_API_KEY + 网络 + akshare;窗口须在最近 ~30 交易日内)
DEEPSEEK_API_KEY=... python scripts/smoke_compare.py 20260529 20260605 1
```
输出含四路对比表 + `HCH−Hexpert` delta + verdict + **HCH 每次 refine 改了什么**(applied/rejected 明细)。
