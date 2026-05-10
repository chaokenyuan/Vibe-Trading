"""共用值物件：Side、OrderIntent、Position、ReservationResult。

所有值物件 SHALL 為 frozen dataclass，保證審計軌跡不可竄改。
事件基底 Event 與具體事件型別在 risk/events.py。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class Side(StrEnum):
    """訂單方向。"""

    BUY = "BUY"
    SELL = "SELL"
    CLOSE = "CLOSE"


@dataclass(frozen=True, kw_only=True)
class OrderIntent:
    """Strategy 產生的下單意圖（尚未過風控閘）。

    回測再現性透過 strategy_id + signal_id + bar_time 三元組保證；
    strategy_version 與 params_hash 由 SignalRouter 在補齊時記錄到 audit log，
    不放此值物件以維持簽名穩定（凍結契約）。
    """

    strategy_id: str
    symbol: str
    side: Side
    qty: Decimal
    price: Decimal | None
    signal_id: str
    bar_time: datetime
    received_at: datetime


@dataclass(frozen=True, kw_only=True)
class Position:
    """LogicalBook 中單一策略對單一標的的持倉視角。

    qty 正值代表 long、負值代表 short、0 代表平倉。
    """

    strategy_id: str
    symbol: str
    qty: Decimal
    avg_entry: Decimal
    opened_at: datetime


@dataclass(frozen=True, kw_only=True)
class ReservationResult:
    """CapitalReserver.reserve() 的回傳。

    成功：ok=True、reservation_id 非空、reason=None、available=None。
    失敗：ok=False、reservation_id=None、reason 與 available 描述不足項。
    """

    ok: bool
    reservation_id: UUID | None
    reason: str | None
    available: Decimal | None


