"""AlertSink Protocol：告警出口抽象。"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AlertSink(Protocol):
    """告警出口。"""

    async def send(
        self,
        *,
        level: str,
        message: str,
        context: dict[str, Any],
    ) -> None: ...
    """發送告警；level 為 info/warning/error/critical。"""
