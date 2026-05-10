"""TelegramAlertSink stub。

用途：把告警推送到 Telegram chat。
輸入：建構參數含 bot token + chat_id；send 接 level/message/context。
輸出：發送到 Telegram bot API。
配置：observability.yaml 的 telegram 區段（後續定義）。
實作策略：
  - 使用 httpx async client 呼叫 Telegram bot API
  - level 對應 emoji prefix（無 emoji 配置時跳過）
  - context 序列化為 markdown code block
  - 失敗時 retry with exponential backoff
本 change 為 stub，凍結介面；後續 change 實作真實 Telegram bot 整合。
"""

from __future__ import annotations

from typing import Any

_NOT_IMPLEMENTED_MSG = (
    "TelegramAlertSink not implemented in add-observability change; "
    "see openspec/changes/<future-change>"
)


class TelegramAlertSink:
    """Telegram bot 告警 stub；結構符合 AlertSink Protocol。"""

    def __init__(
        self,
        *,
        bot_token: str = "",
        chat_id: str = "",
    ) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    async def send(
        self,
        *,
        level: str,
        message: str,
        context: dict[str, Any],
    ) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)
