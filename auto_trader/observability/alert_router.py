"""AlertRouter：訂閱事件 → 過濾關鍵事件 → 轉送 AlertSink。"""

from __future__ import annotations

import logging
from typing import Any

from execution.events import OrderRejectedByBroker
from observability.ports import AlertSink
from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.events import (
    ConfigLoaded,
    DailyPnlReset,
    EmergencyFlattenRequested,
    Event,
    StateChanged,
)

logger = logging.getLogger(__name__)


class AlertRouter:
    """事件 → 告警轉送器。

    內建白名單事件型別 → AlertSink。非白名單事件不告警。
    """

    def __init__(
        self,
        *,
        publisher: InMemoryEventPublisher,
        sink: AlertSink,
    ) -> None:
        self._publisher = publisher
        self._sink = sink

    def start(self) -> None:
        """訂閱所有事件（透過 Event 基底）。"""
        self._publisher.subscribe(Event, self._handle)

    async def _handle(self, event: Event) -> None:
        spec = self._classify(event)
        if spec is None:
            return  # 不告警

        level, message = spec
        try:
            await self._sink.send(
                level=level,
                message=message,
                context=self._build_context(event),
            )
        except Exception:
            logger.exception(
                "alert sink failed: sink=%r event_type=%s",
                self._sink,
                type(event).__name__,
            )

    @staticmethod
    def _classify(event: Event) -> tuple[str, str] | None:
        """白名單匹配：回 (level, message)，None 代表不告警。"""
        if isinstance(event, EmergencyFlattenRequested):
            return ("critical", "KILL_SWITCH triggered: emergency flatten requested")
        if isinstance(event, OrderRejectedByBroker):
            return ("error", f"Order rejected by broker: {event.client_order_id}")
        if isinstance(event, StateChanged):
            level = "warning" if event.to_state in ("HALTED", "THROTTLED") else "info"
            return (level, f"FSM state changed: {event.from_state} → {event.to_state}")
        if isinstance(event, ConfigLoaded):
            return ("info", f"Config loaded: params_hash={event.params_hash[:16]}...")
        if isinstance(event, DailyPnlReset):
            return ("info", "Daily PnL counter reset")
        return None

    @staticmethod
    def _build_context(event: Event) -> dict[str, Any]:
        try:
            return event.to_dict()
        except Exception:
            return {"event_type": type(event).__name__, "event_id": str(event.event_id)}
