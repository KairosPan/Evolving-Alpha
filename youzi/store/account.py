from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PositionState:
    qty_open: int
    avg_cost: float
    realized_pnl: float
    status: str            # open | closed


EMPTY_POSITION = PositionState(qty_open=0, avg_cost=0.0, realized_pnl=0.0, status="open")


def apply_buy(state: PositionState, price: float, qty: int,
              fee: float | None = None) -> PositionState:
    if qty <= 0:
        raise ValueError(f"买入数量须 > 0,got {qty}")
    fee = fee or 0.0
    new_qty = state.qty_open + qty
    new_cost = (state.avg_cost * state.qty_open + price * qty + fee) / new_qty
    return PositionState(qty_open=new_qty, avg_cost=new_cost,
                         realized_pnl=state.realized_pnl, status="open")


def apply_sell(state: PositionState, price: float, qty: int,
               fee: float | None = None) -> PositionState:
    if qty <= 0:
        raise ValueError(f"卖出数量须 > 0,got {qty}")
    if qty > state.qty_open:
        raise ValueError(f"卖出 {qty} 超过持仓 {state.qty_open}")
    fee = fee or 0.0
    pnl = (price - state.avg_cost) * qty - fee
    new_qty = state.qty_open - qty
    return PositionState(qty_open=new_qty, avg_cost=state.avg_cost,
                         realized_pnl=state.realized_pnl + pnl,
                         status="closed" if new_qty == 0 else "open")
