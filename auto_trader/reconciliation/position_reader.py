"""BookPositionReader：實作 risk.ports.PositionReader。

提供 risk-gate 規則所需的 read-only 持倉視圖；資料來源為 StrategyRegistry 的 LogicalBook。
"""

from __future__ import annotations

from risk.types import Position
from strategies.registry import StrategyRegistry


class BookPositionReader:
    """risk.ports.PositionReader 實作（結構性符合）。"""

    def __init__(self, *, registry: StrategyRegistry) -> None:
        self._registry = registry

    def get_position(self, strategy_id: str, symbol: str) -> Position | None:
        book = self._registry.get_book(strategy_id)
        if book is None:
            return None
        logical = book.get_position(symbol)
        if logical is None:
            return None
        return Position(
            strategy_id=logical.strategy_id,
            symbol=logical.symbol,
            qty=logical.qty,
            avg_entry=logical.avg_entry,
            opened_at=logical.opened_at,
        )

    def list_positions(self) -> list[Position]:
        out: list[Position] = []
        for strategy_id in self._registry.list_strategies():
            book = self._registry.get_book(strategy_id)
            if book is None:
                continue
            for logical in book.list_positions():
                out.append(
                    Position(
                        strategy_id=logical.strategy_id,
                        symbol=logical.symbol,
                        qty=logical.qty,
                        avg_entry=logical.avg_entry,
                        opened_at=logical.opened_at,
                    )
                )
        return out
