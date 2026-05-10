"""StrategyRegistry：完整版本（取代 signal-ingestion 的 InMemoryStrategyRegistry stub）。

註冊新策略時自動建立空 LogicalBook、初始狀態為 LOADED。
結構符合 signals.ports.StrategyRegistryProtocol，可直接傳入 SignalRouter。
"""

from __future__ import annotations

from signals.types import StrategyMetadata
from strategies.book import LogicalBook
from strategies.ports import Strategy
from strategies.types import StrategyState


class StrategyRegistry:
    """策略註冊表。"""

    def __init__(self) -> None:
        self._strategies: dict[str, Strategy] = {}
        self._states: dict[str, StrategyState] = {}
        self._books: dict[str, LogicalBook] = {}

    def register(self, strategy: Strategy) -> None:
        """註冊策略到 LOADED 狀態，自動建立空 LogicalBook。"""
        sid = strategy.strategy_id
        self._strategies[sid] = strategy
        self._states[sid] = StrategyState.LOADED
        self._books[sid] = LogicalBook(strategy_id=sid)

    def set_state(self, strategy_id: str, state: StrategyState) -> None:
        if strategy_id not in self._strategies:
            raise KeyError(f"unknown strategy_id: {strategy_id}")
        self._states[strategy_id] = state

    def get_strategy(self, strategy_id: str) -> Strategy | None:
        return self._strategies.get(strategy_id)

    def get_state(self, strategy_id: str) -> StrategyState | None:
        return self._states.get(strategy_id)

    def get_book(self, strategy_id: str) -> LogicalBook | None:
        return self._books.get(strategy_id)

    def list_strategies(self) -> list[str]:
        return list(self._strategies.keys())

    def unregister(self, strategy_id: str) -> bool:
        """移除策略；同時清空 LogicalBook 與 state。

        建議呼叫前先把策略狀態切到 STOPPED 並確認無持倉（書外）。
        Returns: True 若已移除；False 若 strategy_id 不存在。
        """
        if strategy_id not in self._strategies:
            return False
        del self._strategies[strategy_id]
        self._states.pop(strategy_id, None)
        self._books.pop(strategy_id, None)
        return True

    def get_strategy_metadata(
        self, strategy_id: str
    ) -> StrategyMetadata | None:
        """與 signals.ports.StrategyRegistryProtocol 相容的方法。"""
        strategy = self._strategies.get(strategy_id)
        if strategy is None:
            return None
        return strategy.metadata
