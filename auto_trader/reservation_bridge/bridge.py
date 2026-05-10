"""ReservationBridge：client_order_id ↔ reservation_id 對應與自動釋放。"""

from __future__ import annotations

import logging
from collections import OrderedDict
from uuid import UUID

from execution.events import OrderRejectedByBroker, OrderSubmitted
from reconciliation.events import FillProcessed
from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.ports import Clock
from risk.reservation.reserver import CapitalReserver

logger = logging.getLogger(__name__)


class ReservationBridge:
    """訂閱事件、維護 mapping、釋放 reservation。

    使用方式：
        bridge = ReservationBridge(
            publisher=event_publisher,
            reserver=capital_reserver,
            clock=clock,
        )
        bridge.start()
    """

    def __init__(
        self,
        *,
        publisher: InMemoryEventPublisher,
        reserver: CapitalReserver,
        clock: Clock,
        ttl_seconds: int = 86_400,  # 24 hours
        max_entries: int = 100_000,
    ) -> None:
        self._publisher = publisher
        self._reserver = reserver
        self._clock = clock
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        # client_order_id -> (reservation_id, monotonic_recorded_at)
        self._mapping: OrderedDict[str, tuple[UUID, float]] = OrderedDict()

    def start(self) -> None:
        """訂閱所有相關事件。"""
        self._publisher.subscribe(OrderSubmitted, self._on_order_submitted)
        self._publisher.subscribe(OrderRejectedByBroker, self._on_order_rejected)
        self._publisher.subscribe(FillProcessed, self._on_fill_processed)

    @property
    def mapping_size(self) -> int:
        return len(self._mapping)

    async def _on_order_submitted(self, event: OrderSubmitted) -> None:
        if event.reservation_id is None:
            return  # 無 reservation 不需追蹤
        self._mapping[event.client_order_id] = (
            event.reservation_id,
            self._clock.monotonic(),
        )
        # LRU 淘汰
        while len(self._mapping) > self._max_entries:
            self._mapping.popitem(last=False)

    async def _on_order_rejected(self, event: OrderRejectedByBroker) -> None:
        await self._release(event.client_order_id, source="broker_reject")

    async def _on_fill_processed(self, event: FillProcessed) -> None:
        await self._release(event.client_order_id, source="fill")

    async def _release(self, client_order_id: str, *, source: str) -> None:
        entry = self._mapping.get(client_order_id)
        if entry is None:
            logger.warning(
                "no reservation mapping for client_order_id=%s source=%s",
                client_order_id,
                source,
            )
            return

        reservation_id, recorded_at = entry
        # TTL 過期亦不釋放
        if self._clock.monotonic() - recorded_at > self._ttl_seconds:
            logger.warning(
                "reservation mapping expired (TTL %ds): client_order_id=%s",
                self._ttl_seconds,
                client_order_id,
            )
            del self._mapping[client_order_id]
            return

        try:
            await self._reserver.release(reservation_id)
        except Exception:
            logger.exception(
                "reserver.release failed: client_order_id=%s reservation_id=%s",
                client_order_id,
                reservation_id,
            )
            return

        del self._mapping[client_order_id]
