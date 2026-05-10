"""StrategyState、LogicalPosition、Fill 共用值物件。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from risk._serialize import to_json_safe
from risk.types import Side


class StrategyState(StrEnum):
    """Strategy 生命週期狀態。"""

    LOADED = "LOADED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    LIQUIDATING = "LIQUIDATING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


@dataclass(frozen=True, kw_only=True)
class LogicalPosition:
    """LogicalBook 中單一持倉視角（不可變值物件，每次更新建新實例）。

    qty 正值代表 long、負值代表 short、0 代表平倉（會被 LogicalBook 移除而非保留）。
    """

    strategy_id: str
    symbol: str
    qty: Decimal
    avg_entry: Decimal
    opened_at: datetime
    open_signal_id: str

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], to_json_safe(asdict(self)))


@dataclass(frozen=True, kw_only=True)
class Fill:
    """交易所成交回報的標準化形式。

    本 capability 凍結契約；實際 Fill 由 add-order-execution 與
    add-reconciliation capability 產出與消費。
    """

    fill_id: UUID
    client_order_id: str
    broker_order_id: str
    symbol: str
    side: Side
    qty: Decimal
    price: Decimal
    fees: Decimal
    at: datetime

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], to_json_safe(asdict(self)))
