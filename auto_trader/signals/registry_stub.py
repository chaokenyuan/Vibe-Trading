"""StrategyRegistry stub：本 capability 用的最小實作。

完整版本（含註冊／註銷／生命週期事件）由 strategy-host change 提供，
本 stub 僅提供 read API 讓 SignalRouter 可獨立進度。
"""

from __future__ import annotations

from signals.types import StrategyMetadata


class InMemoryStrategyRegistry:
    """記憶體內 StrategyRegistry；結構性符合 StrategyRegistryProtocol。

    本 stub 為測試與 MVP 用途；strategy-host 完整版本將提供熱載入、
    生命週期事件、StrategyState（PAUSED 等）。
    """

    def __init__(self) -> None:
        self._strategies: dict[str, StrategyMetadata] = {}

    def register(self, metadata: StrategyMetadata) -> None:
        """註冊或更新 strategy metadata。"""
        self._strategies[metadata.strategy_id] = metadata

    def get_strategy_metadata(self, strategy_id: str) -> StrategyMetadata | None:
        return self._strategies.get(strategy_id)

    @property
    def known_strategy_ids(self) -> list[str]:
        return list(self._strategies.keys())
