"""PassthroughStrategy：1:1 把 Signal 轉為 OrderIntent，無內部邏輯。

主要用途：
- 測試端到端流程（signal → strategy-host → risk-gate → order-sink）
- 把 TradingView 的判斷直接當成最終訂單（已在 TV 端評估完所有條件）
"""

from __future__ import annotations

from risk.types import OrderIntent, Side
from signals.types import Signal, StrategyMetadata
from strategies.types import Fill


class PassthroughStrategy:
    """直接把 Signal 對應為單一 OrderIntent 的 strategy。

    side 直接沿用 signal（BUY/SELL/CLOSE 全部接受）；
    qty/price/symbol/timestamps 直接拷貝。
    """

    def __init__(
        self,
        *,
        strategy_id: str,
        strategy_version: str,
        params_hash: str,
    ) -> None:
        self._strategy_id = strategy_id
        self._metadata = StrategyMetadata(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            params_hash=params_hash,
        )

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    @property
    def metadata(self) -> StrategyMetadata:
        return self._metadata

    async def on_signal(self, signal: Signal) -> list[OrderIntent]:
        intent = OrderIntent(
            strategy_id=signal.strategy_id,
            symbol=signal.symbol,
            side=Side(signal.side),
            qty=signal.qty,
            price=signal.price,
            signal_id=signal.signal_id,
            bar_time=signal.bar_time,
            received_at=signal.received_at,
        )
        return [intent]

    async def on_fill(self, fill: Fill) -> None:
        # PassthroughStrategy 對 fill 無內部反應；僅供契約完整
        return None
