# youzi_mcp/market.py — youzi-market MCP server(transport 壳,最薄;逻辑在 market_core)。
# 启动:YOUZI_SNAPSHOT=<snap_dir> PYTHONPATH=<repo> python -m youzi_mcp.market
from __future__ import annotations

import json
import os
from datetime import date as Date

from mcp.server.mcpserver import MCPServer

from youzi.data.cache import PITStore
from youzi.data.snapshot_source import SnapshotMissingError, SnapshotSource
from youzi_mcp import market_core as core

mcp = MCPServer("youzi-market")

_ROOT = os.environ.get("YOUZI_SNAPSHOT", "")


def _source() -> SnapshotSource:
    if not _ROOT:
        raise SnapshotMissingError("未设 YOUZI_SNAPSHOT(PIT 快照目录)")
    return SnapshotSource(PITStore(_ROOT))


def _days() -> list[Date]:
    return core.available_days(_ROOT) if _ROOT else []


def _day(day: str) -> Date:
    if day:
        return Date.fromisoformat(day)
    avail = _days()
    if not avail:
        raise SnapshotMissingError(f"快照 {_ROOT or '(未设)'} 无任何交易日数据")
    return avail[-1]


def _j(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _err(msg: str) -> str:
    avail = _days()
    rng = f"{avail[0]}..{avail[-1]}(共 {len(avail)} 个交易日)" if avail else "无"
    return _j({"error": msg, "snapshot_days": rng})


@mcp.tool()
def ping() -> str:
    """连通性测试:返回 youzi-market 服务状态与快照覆盖范围。"""
    avail = _days()
    return _j({
        "status": "ok", "server": "youzi-market", "markets": list(core.KNOWN_MARKETS),
        "snapshot": _ROOT or None,
        "days": f"{avail[0]}..{avail[-1]}" if avail else None,
        "n_days": len(avail),
    })


@mcp.tool()
def market_brief(day: str = "", market: str = "cn") -> str:
    """盘面简报:涨停/炸板/跌停计数、炸板率、最高板、连板梯队。

    数据为 PIT 快照、经防火墙(≤day)。day 格式 YYYY-MM-DD,留空=快照最新交易日。
    market 默认 cn(us/crypto 为预留槽位,尚未接入)。
    """
    if (e := core.market_error(market)) is not None:
        return _err(e)
    try:
        return _j(core.market_brief(_source(), _day(day)))
    except SnapshotMissingError as exc:
        return _err(str(exc))
    except ValueError as exc:
        return _err(f"参数错误:{exc}")


@mcp.tool()
def candidates(day: str = "", market: str = "cn", min_boards: int = 1) -> str:
    """当日涨停候选池(代码/名称/连板数/行业/封单),按连板数降序。

    day 留空=快照最新交易日;min_boards 过滤最低连板数。market 默认 cn(其余为预留槽位)。
    """
    if (e := core.market_error(market)) is not None:
        return _err(e)
    try:
        return _j(core.candidates(_source(), _day(day), min_boards=min_boards))
    except SnapshotMissingError as exc:
        return _err(str(exc))
    except ValueError as exc:
        return _err(f"参数错误:{exc}")


@mcp.tool()
def get_bars(symbol: str, start: str, end: str) -> str:
    """日 K 线(OHLCV)。symbol 形如 'cn:600519'(无前缀默认 cn;前缀是未来市场的槽位)。

    start/end 格式 YYYY-MM-DD。注意:价格为 qfq 前复权(采集时点基准),仅比值安全。
    """
    market, code = core.parse_symbol(symbol)
    if (e := core.market_error(market)) is not None:
        return _err(e)
    if (e := core.validate_cn_code(code)) is not None:
        return _err(e)
    try:
        return _j(core.bars(_source(), code,
                            Date.fromisoformat(start), Date.fromisoformat(end)))
    except SnapshotMissingError as exc:
        return _err(str(exc))
    except ValueError as exc:
        return _err(f"参数错误:{exc}")


if __name__ == "__main__":
    mcp.run()
