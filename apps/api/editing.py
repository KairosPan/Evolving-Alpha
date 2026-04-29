"""Whitelist of editable fields + dirty-node dependency map."""
from __future__ import annotations

import copy
from typing import Any

EDITABLE_PREFIXES: tuple[str, ...] = (
    "pattern_hits",
    "leader_stack",
    "themes.",
    "risk_flags",
)

DIRTY_NODE_MAP: dict[str, str] = {
    "themes":       "theme_analyst",
    "leader_stack": "leader_tracker",
    "pattern_hits": "pattern_matcher",
    "risk_flags":   "risk_guard",
}


class NodeNotEditable(ValueError):
    pass


def validate_path(path: str) -> None:
    if path in {"pattern_hits", "leader_stack", "risk_flags"}:
        return
    if path.startswith("themes.") and path.endswith(".phase"):
        return
    raise NodeNotEditable(f"path '{path}' is not in v1 editable whitelist")


def first_dirty_node(path: str) -> str:
    head = path.split(".", 1)[0]
    if head not in DIRTY_NODE_MAP:
        raise NodeNotEditable(f"no dirty-node mapping for {path}")
    return DIRTY_NODE_MAP[head]


def apply_patch(state: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """Return a deep-copied state with the dotted path set to value."""
    out = copy.deepcopy(state)
    parts = path.split(".")
    cur: Any = out
    for p in parts[:-1]:
        if not isinstance(cur, dict):
            raise NodeNotEditable(f"cannot descend into non-dict at '{p}'")
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value
    return out
