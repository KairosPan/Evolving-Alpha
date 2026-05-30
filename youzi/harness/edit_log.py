from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class EditRecord(BaseModel):
    """一次 Harness 编辑的 Δ 审计记录(蓝图 §4 inner-loop CRUD 轨迹)。"""
    model_config = ConfigDict(frozen=True)
    seq: int
    tool: str                # write_skill / patch_skill / ... / rewrite_doctrine
    target_kind: str         # skill | memory | doctrine
    target_id: str           # skill_id / lesson_id / section
    op: str                  # create | update | retire | dormant | revive | promote | demote | rewrite
    summary: str = ""


class EditLog:
    """单调递增的编辑审计日志(Δ 轨迹);为 Phase-0b-3 版本化/回滚铺路。"""

    def __init__(self) -> None:
        self._records: list[EditRecord] = []

    def append(self, tool: str, target_kind: str, target_id: str,
               op: str, summary: str = "") -> EditRecord:
        rec = EditRecord(seq=len(self._records), tool=tool, target_kind=target_kind,
                         target_id=target_id, op=op, summary=summary)
        self._records.append(rec)
        return rec

    def records(self) -> list[EditRecord]:
        return list(self._records)

    def by_kind(self, target_kind: str) -> list[EditRecord]:
        return [r for r in self._records if r.target_kind == target_kind]

    def by_tool(self, tool: str) -> list[EditRecord]:
        return [r for r in self._records if r.tool == tool]

    def __len__(self) -> int:
        return len(self._records)
