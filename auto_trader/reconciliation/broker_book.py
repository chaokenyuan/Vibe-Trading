"""BrokerPositionTracker：派生自所有策略 LogicalBook 的 broker 視角。"""

from __future__ import annotations

from decimal import Decimal

from strategies.registry import StrategyRegistry


class BrokerPositionTracker:
    """提供 broker 視角的真實持倉（= sum of LogicalBooks per symbol）。

    無內部狀態；每次查詢即時派生。
    """

    def __init__(self, *, registry: StrategyRegistry) -> None:
        self._registry = registry

    def get_total_position(self, symbol: str) -> Decimal:
        total = Decimal("0")
        for strategy_id in self._registry.list_strategies():
            book = self._registry.get_book(strategy_id)
            if book is None:
                continue
            position = book.get_position(symbol)
            if position is not None:
                total += position.qty
        return total

    def list_symbols_with_position(self) -> list[str]:
        symbols: set[str] = set()
        for strategy_id in self._registry.list_strategies():
            book = self._registry.get_book(strategy_id)
            if book is None:
                continue
            for pos in book.list_positions():
                symbols.add(pos.symbol)
        return sorted(symbols)
