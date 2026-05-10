"""FillProcessor：核心 fill 處理。

解 client_order_id → strategy_id → 套到 LogicalBook → 發 FillProcessed 事件。
內部 fill_id 去重快取避免 broker 重送造成重複套用。
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from uuid import UUID

from reconciliation.events import FillProcessed
from risk.ports import Clock, EventPublisher
from strategies.host import StrategyHost
from strategies.registry import StrategyRegistry
from strategies.types import Fill

logger = logging.getLogger(__name__)


class FillProcessor:
    """Fill 處理器。"""

    def __init__(
        self,
        *,
        registry: StrategyRegistry,
        publisher: EventPublisher,
        clock: Clock,
        fill_cache_size: int = 100_000,
    ) -> None:
        self._registry = registry
        self._publisher = publisher
        self._clock = clock
        self._fill_cache_size = fill_cache_size
        # OrderedDict 提供 LRU 行為避免 broker 重送
        self._processed_fills: OrderedDict[UUID, None] = OrderedDict()

    async def on_fill(self, fill: Fill) -> None:
        """主入口；冪等處理同 fill_id。"""
        if fill.fill_id in self._processed_fills:
            logger.debug("duplicate fill_id skipped: %s", fill.fill_id)
            return

        strategy_id = StrategyHost.decode_strategy_id(fill.client_order_id)
        book = self._registry.get_book(strategy_id)
        if book is None:
            logger.warning(
                "fill for unknown strategy: client_order_id=%s strategy_id=%s",
                fill.client_order_id,
                strategy_id,
            )
            return

        book.apply_fill(fill)

        self._processed_fills[fill.fill_id] = None
        while len(self._processed_fills) > self._fill_cache_size:
            self._processed_fills.popitem(last=False)

        await self._publisher.publish(
            FillProcessed(
                at=self._clock.now(),
                fill_id=str(fill.fill_id),
                client_order_id=fill.client_order_id,
                strategy_id=strategy_id,
                symbol=fill.symbol,
            )
        )
