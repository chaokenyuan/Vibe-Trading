"""StateStore 實作集。

MVP 提供 InMemoryStateStore（重啟即丟失）；
後續 change 加 SqliteStateStore 支援跨重啟持久化。
"""

from __future__ import annotations


class InMemoryStateStore:
    """記憶體內 StateStore；結構性符合 risk.ports.StateStore Protocol。

    重啟即丟失。為符合 spec 對「服務重啟讀回先前狀態」的要求，
    生產部署應使用後續 change 提供的 SqliteStateStore。
    """

    def __init__(self) -> None:
        self._state: str | None = None

    def load_state(self) -> str | None:
        return self._state

    def save_state(self, state: str) -> None:
        self._state = state
