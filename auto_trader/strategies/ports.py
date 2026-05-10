"""Strategy Protocol + OrderSink Protocol。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from risk.decision import Decision
from risk.types import OrderIntent
from signals.types import Signal, StrategyMetadata
from strategies.types import Fill


@runtime_checkable
class Strategy(Protocol):
    """單一交易策略抽象。

    name / metadata / strategy_id 為屬性；on_signal 為核心方法。
    """

    @property
    def strategy_id(self) -> str: ...

    @property
    def metadata(self) -> StrategyMetadata: ...

    async def on_signal(self, signal: Signal) -> list[OrderIntent]: ...
    """收到訊號回傳 0–N 筆下單意圖。"""

    async def on_fill(self, fill: Fill) -> None: ...
    """收到自家訂單成交回報；預設可為 no-op。"""


@runtime_checkable
class OrderSink(Protocol):
    """訂單下游接收器抽象。

    本 capability 不提供具體實作；後續 add-order-execution 提供基於 CCXT 的版本。
    """

    async def submit(
        self,
        *,
        intent: OrderIntent,
        decision: Decision,
        client_order_id: str,
    ) -> str: ...
    """提交訂單；回傳交易所 broker_order_id。"""
