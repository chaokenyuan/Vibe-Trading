"""ReservationLedger：三層資金追蹤 + check 純函式 + apply/revert 操作。

對應 spec：「CapitalReserver 為單一 actor 序列化處理預留」。

三道檢查：
1. per-strategy：strategy 可用額度 = max_budget - reserved
2. per-symbol：symbol 集中度上限 = max_concentration - reserved
3. global：總池可用 = total_equity - global_reserved

Ledger 本身不保證並發安全；序列化由 CapitalReserver actor 提供。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class Reservation:
    """單筆預留紀錄（不可變值物件）。"""

    reservation_id: UUID
    strategy_id: str
    symbol: str
    qty: Decimal
    notional: Decimal
    created_at: datetime


@dataclass(frozen=True, kw_only=True)
class CheckResult:
    """check 純函式回傳。

    成功：ok=True、reason=None、available=None。
    失敗：ok=False、reason 為違反項描述、available 為違反道的當前可用額度。
    """

    ok: bool
    reason: str | None
    available: Decimal | None


class ReservationLedger:
    """三層資金 ledger。

    建構參數：
      total_equity：總權益
      strategy_budgets：strategy_id -> max_budget（per-strategy 軟上限）
      symbol_caps：symbol -> max_concentration（per-symbol 集中度上限）

    內部狀態：
      strategy_reserved / symbol_reserved / global_reserved
      reservations：reservation_id -> Reservation
    """

    def __init__(
        self,
        *,
        total_equity: Decimal,
        strategy_budgets: dict[str, Decimal],
        symbol_caps: dict[str, Decimal],
    ) -> None:
        self._total_equity = total_equity
        self._strategy_budgets: dict[str, Decimal] = dict(strategy_budgets)
        self._symbol_caps: dict[str, Decimal] = dict(symbol_caps)
        self._strategy_reserved: dict[str, Decimal] = {
            sid: Decimal("0") for sid in strategy_budgets
        }
        self._symbol_reserved: dict[str, Decimal] = {
            sym: Decimal("0") for sym in symbol_caps
        }
        self._global_reserved: Decimal = Decimal("0")
        self._reservations: dict[UUID, Reservation] = {}

    @property
    def total_equity(self) -> Decimal:
        return self._total_equity

    @property
    def total_reserved(self) -> Decimal:
        return self._global_reserved

    @property
    def total_free(self) -> Decimal:
        return self._total_equity - self._global_reserved

    def strategy_available(self, strategy_id: str) -> Decimal:
        budget = self._strategy_budgets.get(strategy_id, Decimal("0"))
        reserved = self._strategy_reserved.get(strategy_id, Decimal("0"))
        return budget - reserved

    def symbol_available(self, symbol: str) -> Decimal:
        cap = self._symbol_caps.get(symbol)
        if cap is None:
            # 未列入 caps 的 symbol：視為無限額（讓 strategy/global 守關）
            return Decimal("Infinity")
        reserved = self._symbol_reserved.get(symbol, Decimal("0"))
        return cap - reserved

    def check(self, *, strategy_id: str, symbol: str, notional: Decimal) -> CheckResult:
        """純函式：判斷是否可預留 notional 金額。不修改 ledger。"""
        if strategy_id not in self._strategy_budgets:
            return CheckResult(
                ok=False,
                reason="strategy_unknown",
                available=Decimal("0"),
            )

        strategy_avail = self.strategy_available(strategy_id)
        if notional > strategy_avail:
            return CheckResult(
                ok=False,
                reason="strategy_budget_insufficient",
                available=strategy_avail,
            )

        symbol_avail = self.symbol_available(symbol)
        if notional > symbol_avail:
            return CheckResult(
                ok=False,
                reason="symbol_concentration_insufficient",
                available=symbol_avail,
            )

        if notional > self.total_free:
            return CheckResult(
                ok=False,
                reason="global_capital_insufficient",
                available=self.total_free,
            )

        return CheckResult(ok=True, reason=None, available=None)

    def apply(self, reservation: Reservation) -> None:
        """套用預留：更新三層 reserved 並登記 reservation。

        呼叫前 SHALL 已通過 check；違反 invariant 時拋例外。
        """
        if reservation.reservation_id in self._reservations:
            raise ValueError(f"reservation_id duplicate: {reservation.reservation_id}")

        sid = reservation.strategy_id
        sym = reservation.symbol
        amount = reservation.notional

        self._strategy_reserved[sid] = (
            self._strategy_reserved.get(sid, Decimal("0")) + amount
        )
        if sym in self._symbol_caps:
            self._symbol_reserved[sym] = (
                self._symbol_reserved.get(sym, Decimal("0")) + amount
            )
        self._global_reserved += amount
        self._reservations[reservation.reservation_id] = reservation

    def revert(self, reservation_id: UUID) -> Reservation | None:
        """釋放預留；若已釋放或不存在回傳 None（冪等）。"""
        reservation = self._reservations.pop(reservation_id, None)
        if reservation is None:
            return None

        sid = reservation.strategy_id
        sym = reservation.symbol
        amount = reservation.notional

        self._strategy_reserved[sid] = (
            self._strategy_reserved.get(sid, Decimal("0")) - amount
        )
        if sym in self._symbol_caps:
            self._symbol_reserved[sym] = (
                self._symbol_reserved.get(sym, Decimal("0")) - amount
            )
        self._global_reserved -= amount
        return reservation

    def has_reservation(self, reservation_id: UUID) -> bool:
        return reservation_id in self._reservations
