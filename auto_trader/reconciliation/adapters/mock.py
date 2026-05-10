"""MockFillSource：手動 push API 的 FillSource 實作。"""

from __future__ import annotations

from reconciliation.ports import FillCallback
from strategies.types import Fill


class MockFillSource:
    """測試 / dry-run 用的 FillSource。

    建構時注入 callback，呼叫 push(fill) 即觸發 callback。
    結構性符合 reconciliation.ports.FillSource Protocol。
    """

    def __init__(self, *, callback: FillCallback) -> None:
        self._callback = callback
        self._started = False

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False

    async def push(self, fill: Fill) -> None:
        """測試呼叫：手動推送 fill 給 callback。"""
        if not self._started:
            raise RuntimeError("MockFillSource not started")
        await self._callback(fill)
