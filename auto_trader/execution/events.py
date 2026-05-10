"""order-execution capability 發布的事件。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from risk.events import Event


@dataclass(frozen=True, kw_only=True)
class OrderSubmitted(Event):
    """訂單已成功提交至交易所。

    reservation_id 為對應 RiskGate Decision 的預留 ID（可為 None：
    若風控未啟用 CapitalReservationRule 或 reservation 未取得）。
    供 reservation-release capability 維護 client_order_id ↔ reservation_id mapping。
    """

    client_order_id: str
    broker_order_id: str
    symbol: str
    strategy_id: str
    reservation_id: UUID | None = None


@dataclass(frozen=True, kw_only=True)
class OrderRejectedByBroker(Event):
    """訂單被交易所拒絕（網路、餘額不足、symbol 無效等）。"""

    client_order_id: str
    symbol: str
    strategy_id: str
    reason: str
