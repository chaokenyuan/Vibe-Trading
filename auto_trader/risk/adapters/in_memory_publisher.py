"""InMemoryEventPublisher：記憶體內 fan-out 的事件總線。

對應 spec：「事件發布到所有訂閱者、訂閱者間無耦合」。

訂閱語意：
- 訂閱具體事件型別（如 StateChanged）→ 只接收該型別事件
- 訂閱 Event 基底 → 接收所有事件（適合 audit / observability）
- 透過 type(event).__mro__ 走訪實作

故障隔離：
- 任一訂閱者拋例外時，其他訂閱者仍正常呼叫
- 例外透過 stdlib logging 記錄，不向上拋
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from risk.events import Event

logger = logging.getLogger(__name__)

E = TypeVar("E", bound=Event)
Handler = Callable[[Event], Awaitable[None]]


class InMemoryEventPublisher:
    """記憶體內事件總線；結構性符合 risk.ports.EventPublisher Protocol。"""

    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[Handler]] = {}

    def subscribe(self, event_type: type[E], handler: Callable[[E], Awaitable[None]]) -> None:
        """訂閱指定事件型別。同一 handler 重複訂閱會被各自記錄並各自呼叫。

        訂閱 Event 基底等於訂閱所有事件。
        """
        # 型別擦除：對外暴露具體型別 handler，內部以 Event 統一
        self._handlers.setdefault(event_type, []).append(handler)  # type: ignore[arg-type]

    async def publish(self, event: Event) -> None:
        """發布事件至所有訂閱者（依事件型別 MRO 由具體至基底走訪）。

        訂閱者間故障隔離：任一 handler 例外不影響其他 handler。
        """
        for cls in type(event).__mro__:
            if cls is object:
                continue
            for handler in self._handlers.get(cls, []):
                try:
                    await handler(event)
                except Exception:
                    logger.exception(
                        "subscriber failed: handler=%r event_type=%s event_id=%s",
                        handler,
                        type(event).__name__,
                        event.event_id,
                    )
