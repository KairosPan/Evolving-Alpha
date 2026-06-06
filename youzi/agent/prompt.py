from __future__ import annotations

from youzi.harness.harness import HarnessState
from youzi.schemas.market import MarketState
from youzi.universe.universe import CandidateUniverse

_OUTPUT_CONTRACT = (
    '输出格式(严格 JSON,不要 markdown 围栏):'
    '{"regime_read": "<当前情绪相位>", '
    '"candidates": [{"code": "<6位代码,必须来自候选池>", "pattern": "<命中的模式名/skill_id>", '
    '"reason": "<简短理由>", "confidence": <0到1的小数>}], '
    '"no_trade_reason": "<若判断空仓则填理由,否则空字符串>"}'
)


def build_system_prompt(h: HarnessState) -> str:
    """把 H=(p,K,M)+状态机渲染成系统提示——harness 包住模型的核心。"""
    out: list[str] = [
        "你是 A股游资/超短交易 co-pilot。读当日盘面与候选池,依据下面的纪律红线、作战 doctrine、"
        "情绪周期、模式库与复盘教训,判读当前相位并产出一个决策包 JSON。人类游资会确认后下单。",
        "\n## 纪律红线(绝对遵守,违背即错):",
    ]
    for e in h.doctrine.immutable_core():
        out.append(f"- {e.section}:{e.guidance}")
    out.append("\n## 作战 doctrine(按相位):")
    for e in h.doctrine.mutable_entries():
        out.append(f"- [{e.regime_raw or 'all'}] {e.section}:{e.guidance}")
    out.append("\n## 情绪周期相位(据此判读 regime_read):")
    for p in h.cycle.phases:
        sigs = ";".join(f"{t.signal}→{t.to}" for t in p.transitions)
        out.append(f"- {p.phase}:你看到[{'/'.join(p.you_see)}] 转移[{sigs}]")
    out.append("\n## 模式库(可用技能,只在适用相位用):")
    for s in h.skills.by_status("active"):
        tags = "/".join(s.phases) + (("|" + "/".join(s.ecologies)) if s.ecologies else "")
        line = (f"- {s.name_cn}({s.skill_id})[{s.type}] 适用[{tags}] "
                f"触发:{s.trigger} 买点:{s.entry} 卖/止:{s.exit_stop} "
                f"禁忌:{';'.join(s.taboo)}")
        st = s.stats
        if st.n > 0:                                   # 有战绩才渲染,让 agent 看到亏/被砸
            bits = f"n={st.n}"
            if st.ewma_winrate is not None:
                bits += f" 胜率={st.ewma_winrate:.2f}"
            bits += f" nukes={st.nukes}"
            if st.expectancy is not None:
                bits += f" exp={st.expectancy:+.2f}"
            line += f" [战绩 {bits}]"
        out.append(line)
    out.append("\n## 复盘教训(口诀与失败签名):")
    for l in h.memory.all():
        if l.outcome == "principle":
            out.append(f"- [口诀] {l.lesson}")
    for l in h.memory.all():
        if l.outcome == "loss":
            tag = f"{l.named_analog}:" if l.named_analog else ""
            out.append(f"- [失败] {tag}{l.lesson}")
    for l in h.memory.all():
        if l.outcome == "win":
            tag = f"{l.named_analog}:" if l.named_analog else ""
            out.append(f"- [成功] {tag}{l.lesson}")
    out.append("\n## " + _OUTPUT_CONTRACT)
    return "\n".join(out)


def build_user_prompt(state: MarketState, universe: CandidateUniverse) -> str:
    """渲染当日盘面 + 候选池(只能从候选池里选 code)。"""
    out = [
        f"## 今日盘面 {state.date}:",
        f"情绪值(归一):{state.sentiment_norm}  原始复合分:{state.sentiment_raw:.1f}",
        f"最高连板:{state.max_board_height}  涨停数:{state.limit_up_count}  "
        f"炸板率:{state.blowup_rate:.2f}  跌停数:{state.limit_down_count}",
        f"赚钱效应(昨涨停今表现均值):{state.money_effect_raw:.2f}",
    ]
    if state.echelon:
        ech = ";".join(f"{r.height}板×{r.count}({'/'.join(r.representatives)})"
                       for r in state.echelon)
        out.append(f"连板梯队:{ech}")
    out.append("\n## 候选池(只能从这里面选 code;名 连板 行业):")
    ups = sorted(universe.by_status("limit_up"), key=lambda s: -(s.boards or 0))
    for s in ups:
        out.append(f"- {s.code} {s.name} {s.boards or '?'}板 {s.industry or ''}")
    if not ups:
        out.append("(今日无涨停候选)")
    return "\n".join(out)
