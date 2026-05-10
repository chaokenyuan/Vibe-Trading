"""ExecutionAdapter Protocol：交易所 SDK 抽象。

對外暴露 submit / cancel；具體交易所差異全部封裝在 adapter 內部。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from risk.types import OrderIntent


@runtime_checkable
class ExecutionAdapter(Protocol):
    """交易所 SDK 抽象。"""

    async def submit(
        self,
        *,
        intent: OrderIntent,
        client_order_id: str,
    ) -> str: ...
    """提交訂單；回傳交易所 broker_order_id。失敗 SHALL raise。"""

    async def cancel(self, broker_order_id: str) -> None: ...
    """取消指定 broker_order_id；無法取消 SHALL raise。"""
