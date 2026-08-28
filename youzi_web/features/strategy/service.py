# youzi_web/features/strategy/service.py
from __future__ import annotations

import math

from youzi_mcp import harness_core as core   # web / dsh 两壳共用的 H 读模型
from youzi_web.data_access import seed_harness

CANONICAL_STATUSES = ("active", "incubating", "dormant", "retired")


def h():
    return seed_harness()


def skills_context(phase: str | None, status: str | None) -> dict:
    hs = h()
    return {
        "phase": phase or "", "status": status or "",
        "phases": [p.phase for p in hs.cycle.phases],
        "statuses": CANONICAL_STATUSES,
        "skills": core.skills_view(hs, phase=phase or None, status=status or None),
        "lens": core.lens_view(hs, phase) if phase else None,
    }


def doctrine_context() -> dict:
    hs = h()
    return {"doctrine": core.doctrine_view(hs), "lessons": core.memory_view(hs)}


def cycle_ring(size: int = 420) -> dict:
    """7 相位环几何(纯函数):节点坐标 + 转移连线。相位按种子状态机顺序排环。"""
    hs = h()
    phases = core.cycle_view(hs)
    n = len(phases)
    cx = cy = size / 2
    r = size / 2 - 58
    pos: dict[str, tuple[float, float]] = {}
    nodes = []
    for i, p in enumerate(phases):
        ang = 2 * math.pi * i / n - math.pi / 2
        x, y = cx + r * math.cos(ang), cy + r * math.sin(ang)
        pos[p["phase"]] = (x, y)
        nodes.append({"phase": p["phase"], "x": round(x, 1), "y": round(y, 1),
                      "you_see": p["you_see"], "transitions": p["transitions"]})
    edges = []
    for p in phases:
        x1, y1 = pos[p["phase"]]
        for t in p["transitions"]:
            if t["to"] in pos:
                x2, y2 = pos[t["to"]]
                # 缩短线段避免压住节点圆
                dx, dy = x2 - x1, y2 - y1
                d = math.hypot(dx, dy) or 1.0
                pad = 34
                edges.append({
                    "x1": round(x1 + dx / d * pad, 1), "y1": round(y1 + dy / d * pad, 1),
                    "x2": round(x2 - dx / d * pad, 1), "y2": round(y2 - dy / d * pad, 1),
                })
    return {"size": size, "nodes": nodes, "edges": edges}
