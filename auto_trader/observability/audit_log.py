"""AuditLogWriter：訂閱 EventPublisher 把所有事件寫成 JSON Lines。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.events import Event

logger = logging.getLogger(__name__)


class AuditLogWriter:
    """事件稽核寫入器。

    建構時注入 publisher 與檔案路徑；start 訂閱 Event 基底（接收所有事件）。
    每筆事件：呼叫 event.to_dict() → json.dumps → 追加一行至檔案。
    任一筆序列化失敗：紀錄 error 不向上拋，後續事件繼續。
    """

    def __init__(
        self,
        *,
        publisher: InMemoryEventPublisher,
        log_path: str | Path,
    ) -> None:
        self._publisher = publisher
        self._log_path = Path(log_path)
        # 確保目錄存在
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        """訂閱 Event 基底；所有事件型別都會經過。"""
        self._publisher.subscribe(Event, self._handle)

    async def _handle(self, event: Event) -> None:
        try:
            payload = event.to_dict()
            line = json.dumps(payload, ensure_ascii=False)
        except Exception:
            logger.exception(
                "failed to serialize event for audit log: type=%s",
                type(event).__name__,
            )
            return

        try:
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            logger.exception("failed to append audit log: path=%s", self._log_path)

    @property
    def log_path(self) -> Path:
        return self._log_path
