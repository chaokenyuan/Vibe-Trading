"""LoggingAlertSink：用 stdlib logging 輸出告警。

對應 spec：「AlertSink Protocol 統一告警出口」、「LoggingAlertSink 為完整實作」。
生產可用：日誌系統（journalctl / docker logs / ELK）會收集。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("vibe.alerts")

LEVEL_MAP = {
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


class LoggingAlertSink:
    """用 stdlib logging 的 AlertSink 實作。"""

    async def send(
        self,
        *,
        level: str,
        message: str,
        context: dict[str, Any],
    ) -> None:
        log_level = LEVEL_MAP.get(level.lower(), logging.WARNING)
        logger.log(log_level, "%s | context=%r", message, context)
