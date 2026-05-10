"""reconciliation capability 發布的事件。"""

from __future__ import annotations

from dataclasses import dataclass

from risk.events import Event


@dataclass(frozen=True, kw_only=True)
class FillProcessed(Event):
    """Fill 已處理並套用到對應策略的 LogicalBook。"""

    fill_id: str
    client_order_id: str
    strategy_id: str
    symbol: str
