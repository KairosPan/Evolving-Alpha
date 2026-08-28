# youzi/store/errors.py
"""仓储层错误类型。web 层按类型映射 HTTP 码(409/404/422),领域层不认 HTTP。"""
from __future__ import annotations


class StoreError(RuntimeError):
    """仓储层错误根类。"""


class IllegalTransitionError(StoreError):
    """非法状态转移(如 succeeded → running、重复 adopt)。→ HTTP 409。"""


class DuplicateError(StoreError):
    """唯一约束冲突(如同账户同交易日已有 ops_session)。→ HTTP 409。"""


class NotFoundError(StoreError):
    """目标记录不存在。→ HTTP 404。"""
