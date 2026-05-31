from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

StockStatus = Literal["limit_up", "blowup", "limit_down"]


class StockSnapshot(BaseModel):
    """个股当日 PIT 快照(frozen)。status 来自所属池(收盘三池互斥)。缺失字段 None。"""
    model_config = ConfigDict(frozen=True)
    code: str
    name: str
    status: StockStatus
    boards: int = 0                       # 连板数(跌停/炸板可能为 0)
    pct: float | None = None              # 今涨跌幅(%)
    seal_amount: float | None = None      # 封板资金
    turnover_rate: float | None = None    # 换手率(%)
    first_seal_time: str | None = None    # 首次封板时间
    blowup_count: int | None = None       # 炸板次数
    industry: str | None = None           # 所属行业
    float_mcap: float | None = None       # 流通市值
