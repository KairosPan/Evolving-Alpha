# youzi/store/
"""live 事务域仓储层(SQLite,stdlib sqlite3,不引 ORM)。

与既有 PIT Parquet(`youzi/data/cache.py`)分工:Parquet 存**市场事实**(只增不改、
列式重读),本包存 **live 事务**(agent 运行 / 人工确认 / 成交 / 账户快照)——需要
唯一约束、状态机、事务原子性,parquet 给不了。

纯仓储:只做取存与约束强制,不做业务编排(编排在 `youzi/application/`)。
"""
from youzi.store.db import SCHEMA_VERSION, connect, db_path, init_schema
from youzi.store.errors import (
    DuplicateError,
    IllegalTransitionError,
    NotFoundError,
    StoreError,
)

__all__ = [
    "SCHEMA_VERSION", "connect", "db_path", "init_schema",
    "StoreError", "IllegalTransitionError", "DuplicateError", "NotFoundError",
]
