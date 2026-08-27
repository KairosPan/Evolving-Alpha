# youzi_mcp/harness_core.py — 策略(H)读模型:web / dsh 两壳共用(纯函数、零 MCP 依赖)。
# 只读投影,不 mutate H;相位透镜直接复用 agent 的 select_for_prompt——展示的就是注入的。
from __future__ import annotations

from youzi.agent.retrieval import select_for_prompt
from youzi.harness.harness import HarnessState
from youzi.harness.memory_item import Lesson
from youzi.harness.skill import Skill


def skill_row(s: Skill) -> dict:
    st = s.stats
    n = st.n
    return {
        "skill_id": s.skill_id, "name_cn": s.name_cn, "type": s.type,
        "status": s.status, "phases": list(s.phases), "ecologies": list(s.ecologies),
        "applies_all": s.applies_all,
        "trigger": s.trigger, "entry": s.entry, "exit_stop": s.exit_stop,
        "taboo": list(s.taboo),
        "stats": {
            "n": n, "wins": st.wins, "losses": st.losses, "nukes": st.nukes,
            "ewma_winrate": st.ewma_winrate,
            "expectancy": st.expectancy,          # 语义=advantage(C2 起,超额)
            "hit_rate": (st.wins / n) if n else None,
            "nuke_rate": (st.nukes / n) if n else None,
        },
    }


def skills_view(h: HarnessState, phase: str | None = None,
                status: str | None = None) -> list[dict]:
    skills = h.skills.by_phase(phase) if phase else h.skills.all()
    if status:
        skills = [s for s in skills if s.status == status]
    return [skill_row(s) for s in skills]


def doctrine_view(h: HarnessState) -> dict:
    def row(e) -> dict:
        return {"section": e.section, "guidance": e.guidance,
                "regime": e.regime_raw or "all", "immutable": e.immutable}
    return {"immutable": [row(e) for e in h.doctrine.immutable_core()],
            "mutable": [row(e) for e in h.doctrine.mutable_entries()]}


def lesson_row(l: Lesson) -> dict:
    return {"lesson_id": l.lesson_id, "outcome": l.outcome, "lesson": l.lesson,
            "named_analog": l.named_analog, "phases": list(l.phases),
            "ecologies": list(l.ecologies),
            "weight": round(l.importance.weight(), 4)}


def memory_view(h: HarnessState) -> list[dict]:
    return sorted((lesson_row(l) for l in h.memory.all()),
                  key=lambda r: -r["weight"])


def cycle_view(h: HarnessState) -> list[dict]:
    return [{"phase": p.phase, "you_see": list(p.you_see),
             "transitions": [{"signal": t.signal, "to": t.to} for t in p.transitions]}
            for p in h.cycle.phases]


def lens_view(h: HarnessState, phase: str) -> dict:
    """相位透镜:该相位下 agent 被实际注入的选集(预算内 top-B + 试验位 + 记忆)。"""
    sel = select_for_prompt(h, phase_prior=phase)
    return {"phase": phase,
            "skills": [skill_row(s) for s in sel.skills],
            "trials": [skill_row(s) for s in sel.trials],
            "lessons": [lesson_row(l) for l in sel.lessons]}
