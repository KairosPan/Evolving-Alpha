"""Helpers to fold lists in MarketState reducers."""
from __future__ import annotations

from .state import Candidate


def dedupe_candidates_by_code(candidates: list[Candidate]) -> list[Candidate]:
    """Keep the highest-score candidate per stock code."""
    best: dict[str, Candidate] = {}
    for c in candidates:
        prev = best.get(c["code"])
        if prev is None or c.get("score", 0) > prev.get("score", 0):
            best[c["code"]] = c
    return sorted(best.values(), key=lambda x: -x.get("score", 0))
