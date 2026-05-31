from __future__ import annotations

from youzi.universe.stock import StockSnapshot


class CandidateUniverse:
    """某交易日按 code 索引的候选个股集合(涨停/炸板/跌停)。"""

    def __init__(self, stocks: dict[str, StockSnapshot]) -> None:
        self._stocks = dict(stocks)          # 防御性拷贝

    @classmethod
    def from_stocks(cls, stocks: list[StockSnapshot]) -> "CandidateUniverse":
        index: dict[str, StockSnapshot] = {}
        for s in stocks:
            if s.code in index:
                raise ValueError(f"重复 code: {s.code}")
            index[s.code] = s
        return cls(index)

    def get(self, code: str) -> StockSnapshot | None:
        return self._stocks.get(code)

    def all(self) -> list[StockSnapshot]:
        return list(self._stocks.values())

    def by_status(self, status: str) -> list[StockSnapshot]:
        return [s for s in self._stocks.values() if s.status == status]

    def by_min_boards(self, n: int) -> list[StockSnapshot]:
        return [s for s in self._stocks.values() if s.boards >= n]

    def by_industry(self, industry: str) -> list[StockSnapshot]:
        return [s for s in self._stocks.values() if s.industry == industry]

    def __len__(self) -> int:
        return len(self._stocks)

    def __bool__(self) -> bool:
        return True              # 空但存在的 universe 仍为真(杀 falsy-trap)
