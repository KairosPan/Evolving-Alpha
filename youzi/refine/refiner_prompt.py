# youzi/refine/refiner_prompt.py
from __future__ import annotations

from youzi.eval.trajectory import Trajectory
from youzi.harness.harness import HarnessState
from youzi.refine.credit import CreditReport
from youzi.refine.ops import PassKind
from youzi.refine.signatures import FailureSignature

_PASS_DESC: dict[str, str] = {
    "p": "改写 mutable 作战 doctrine(纪律红线 immutable 改不动,试图改写会被拒绝)",
    "K": "增删改技能库 K(write/patch/retire/revive/promote)",
    "M": "增删改复盘记忆 M(process/update/demote)",
}

_PASS_TOOLS_DOC: dict[str, str] = {
    "p": '- rewrite_doctrine: {"section": "<已存在的 mutable 段名>", "new_guidance": "<新指导>"}',
    "K": ('- write_skill: {"skill_id","name_cn","type":"pattern|feature|failure_detector",'
          '"applicable_regime":[...],"trigger","entry","exit_stop","taboo":[...],"status":"incubating"}\n'
          '- patch_skill: {"skill_id","<字段>":<值>,...}(不可改 status/phases/ecologies)\n'
          '- retire_skill: {"skill_id","permanent":false}\n'
          '- revive_skill: {"skill_id"}(仅 dormant→incubating)\n'
          '- promote_skill: {"skill_id"}(仅 incubating→active)'),
    "M": ('- process_memory: {"lesson_id","regime","outcome":"win|loss|principle","lesson",'
          '"pattern","failure_signature","named_analog"}\n'
          '- update_memory: {"lesson_id","<字段>":<值>,...}\n'
          '- demote_memory: {"lesson_id","factor":<0~1 之间>}'),
}


def build_refiner_system_prompt(h: HarnessState, pass_kind: PassKind) -> str:
    """某 pass 的复盘官系统提示:本 pass 改哪个容器 + 可用 meta-tool schema + 规则 + 当前 H 切片。"""
    out = [
        "你是 A股游资/超短交易系统的**复盘官(Refiner)**。读最近复盘窗口的决策与已实现结果、"
        "技能信用、失败签名,据此对当前打法 H 做**结构性编辑**,让系统下次更强。",
        f"\n## 本轮只允许:{_PASS_DESC[pass_kind]}",
        "## 可用编辑(严格按参数 schema):",
        _PASS_TOOLS_DOC[pass_kind],
        "\n## 规则:",
        "- 纪律红线(immutable)绝对改不动,试图改写会被拒绝。",
        "- 每条编辑必须带非空 rationale(理由),否则被拒绝。",
        "- 谨慎、少而精;只在证据充分时编辑,无可改则给空列表。",
    ]
    if pass_kind == "p":
        out.append("\n## 当前 mutable doctrine(可改写):")
        for e in h.doctrine.mutable_entries():
            out.append(f"- {e.section}: {e.guidance}")
        out.append("## 纪律红线(immutable,改不动,仅供参考):")
        for e in h.doctrine.immutable_core():
            out.append(f"- {e.section}: {e.guidance}")
    elif pass_kind == "K":
        out.append("\n## 当前技能(含战绩):")
        for s in h.skills.all():
            st = s.stats
            perf = f" [n={st.n} nukes={st.nukes}]" if st.n > 0 else ""
            out.append(f"- {s.skill_id}({s.name_cn})[{s.type}/{s.status}]{perf}")
    elif pass_kind == "M":
        out.append("\n## 当前记忆:")
        for l in h.memory.all():
            out.append(f"- {l.lesson_id}[{l.outcome}]: {l.lesson}")
    out.append('\n## 输出严格 JSON(无 markdown 围栏):'
               '{"ops": [{"tool": "...", "args": {...}, "rationale": "..."}]}')
    return "\n".join(out)


def build_refiner_user_prompt(traj: Trajectory, credit: CreditReport,
                              signatures: list[FailureSignature], window: int = 10) -> str:
    """渲染证据:最近 window 步决策→结果 + 技能信用 + 失败签名。"""
    out = ["## 最近复盘窗口(决策 → 已实现结果):"]
    for st in traj.scored_steps()[-window:]:
        picks = ", ".join(f"{c.code}({c.pattern})" for c in st.decision.candidates) or "空仓"
        outs = ", ".join(f"{code}:{sc.outcome}" for code, sc in st.outcomes.items()) or "—"
        out.append(f"- {st.date} 选[{picks}] → {outs}")

    out.append("\n## 技能信用(本轮谁在亏):")
    if credit.per_skill:
        for sid, c in credit.per_skill.items():
            out.append(f"- {sid}: n={c.n} 胜率={c.hit_rate:.2f} "
                       f"nuke率={c.nuke_rate:.2f} exp={c.expectancy:+.2f}")
    else:
        out.append("(无)")
    if credit.unattributed:
        u = credit.unattributed
        out.append(f"- [未归因] n={u.n} 胜率={u.hit_rate:.2f} exp={u.expectancy:+.2f}")

    out.append("\n## 失败签名(入场坑):")
    if signatures:
        for s in signatures:
            out.append(f"- {s.date} {s.code} [{s.kind}] pattern={s.pattern} "
                       f"skill={s.skill_id or '?'}: {s.evidence}")
    else:
        out.append("(无)")
    return "\n".join(out)
