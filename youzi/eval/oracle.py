from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from typing import Literal

from youzi.universe.universe import CandidateUniverse

Outcome = Literal["continued", "faded", "nuked"]

SCORE: dict[str, float] = {"continued": 1.0, "faded": 0.0, "nuked": -1.0}


@dataclass(frozen=True)
class DayMembership:
    """某交易日三池的 code 成员(用于事后判定被选标的的结果)。"""
    limit_up: frozenset[str]
    blowup: frozenset[str]
    limit_down: frozenset[str]


class PoolRecord:
    """按交易日录制 pool 成员;walk-forward 每到一个游标录一天(只录 ≤ 游标)。"""

    def __init__(self) -> None:
        self._by_day: dict[Date, DayMembership] = {}

    def record(self, day: Date, universe: CandidateUniverse) -> None:
        self._by_day[day] = DayMembership(
            limit_up=frozenset(s.code for s in universe.by_status("limit_up")),
            blowup=frozenset(s.code for s in universe.by_status("blowup")),
            limit_down=frozenset(s.code for s in universe.by_status("limit_down")),
        )

    def get(self, day: Date) -> DayMembership | None:
        return self._by_day.get(day)


def outcome(code: str, mem: DayMembership) -> Outcome:
    """已实现未来类别:horizon 天后该 code 在哪个池。跌停/炸板优先判 nuked。"""
    if code in mem.limit_down or code in mem.blowup:
        return "nuked"
    if code in mem.limit_up:
        return "continued"
    return "faded"
