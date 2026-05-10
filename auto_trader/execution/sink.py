"""ExchangeOrderSink：strategies.ports.OrderSink 的具體實作。"""

from __future__ import annotations

import logging

from execution.events import OrderRejectedByBroker, OrderSubmitted
from execution.ports import ExecutionAdapter
from risk.decision import Decision
from risk.ports import Clock, EventPublisher
from risk.types import OrderIntent

logger = logging.getLogger(__name__)


class ExchangeOrderSink:
    """OrderSink 實作。結構性符合 strategies.ports.OrderSink Protocol。"""

    def __init__(
        self,
        *,
        adapter: ExecutionAdapter,
        publisher: EventPublisher,
        clock: Clock,
    ) -> None:
        self._adapter = adapter
        self._publisher = publisher
        self._clock = clock

    async def submit(
        self,
        *,
        intent: OrderIntent,
        decision: Decision,
        client_order_id: str,
    ) -> str:
        """提交訂單；發布 OrderSubmitted 或 OrderRejectedByBroker。"""
        try:
            broker_order_id = await self._adapter.submit(
                intent=intent,
                client_order_id=client_order_id,
            )
        except Exception as exc:
            await self._publisher.publish(
                OrderRejectedByBroker(
                    at=self._clock.now(),
                    client_order_id=client_order_id,
                    symbol=intent.symbol,
                    strategy_id=intent.strategy_id,
                    reason=str(exc),
                )
            )
            logger.exception(
                "broker rejected order: client_order_id=%s",
                client_order_id,
            )
            raise

        await self._publisher.publish(
            OrderSubmitted(
                at=self._clock.now(),
                client_order_id=client_order_id,
                broker_order_id=broker_order_id,
                symbol=intent.symbol,
                strategy_id=intent.strategy_id,
                reservation_id=decision.reservation_id,
            )
        )
        return broker_order_id
