"""ReservationLedger 單元測試。

對應 spec scenario：
- 三道全通過則成功預留
- 任一不足則拒絕（per-strategy / per-symbol / global）
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from risk.reservation.ledger import Reservation, ReservationLedger


def _ledger() -> ReservationLedger:
    return ReservationLedger(
        total_equity=Decimal("10000"),
        strategy_budgets={"A": Decimal("5000"), "B": Decimal("4000")},
        symbol_caps={"BTCUSDT": Decimal("4000"), "ETHUSDT": Decimal("3000")},
    )


def _reservation(
    strategy_id: str = "A",
    symbol: str = "BTCUSDT",
    notional: Decimal = Decimal("1000"),
) -> Reservation:
    return Reservation(
        reservation_id=uuid4(),
        strategy_id=strategy_id,
        symbol=symbol,
        qty=Decimal("1"),
        notional=notional,
        created_at=datetime(2026, 5, 10, tzinfo=UTC),
    )


# ===== check 純函式 =====


def test_check_passes_when_all_three_layers_have_capacity() -> None:
    ledger = _ledger()
    result = ledger.check(strategy_id="A", symbol="BTCUSDT", notional=Decimal("1000"))
    assert result.ok is True
    assert result.reason is None


def test_check_rejects_unknown_strategy() -> None:
    ledger = _ledger()
    result = ledger.check(strategy_id="UNKNOWN", symbol="BTCUSDT", notional=Decimal("100"))
    assert result.ok is False
    assert result.reason == "strategy_unknown"


def test_check_rejects_when_strategy_budget_insufficient() -> None:
    ledger = _ledger()
    # A 預算 5000，請求 6000
    result = ledger.check(strategy_id="A", symbol="BTCUSDT", notional=Decimal("6000"))
    assert result.ok is False
    assert result.reason == "strategy_budget_insufficient"
    assert result.available == Decimal("5000")


def test_check_rejects_when_symbol_concentration_insufficient() -> None:
    """A 預算夠（50000），但 BTC symbol 上限 4000 不夠。"""
    big_ledger = ReservationLedger(
        total_equity=Decimal("100000"),
        strategy_budgets={"A": Decimal("50000")},
        symbol_caps={"BTCUSDT": Decimal("4000")},
    )
    result = big_ledger.check(
        strategy_id="A", symbol="BTCUSDT", notional=Decimal("4500")
    )
    assert result.ok is False
    assert result.reason == "symbol_concentration_insufficient"
    assert result.available == Decimal("4000")


def test_check_rejects_when_global_capital_insufficient() -> None:
    """三道：strategy 與 symbol 都通過，但 global 不夠（例：兩策略都已預留）。"""
    ledger = ReservationLedger(
        total_equity=Decimal("1000"),
        strategy_budgets={"A": Decimal("800"), "B": Decimal("800")},
        symbol_caps={"BTCUSDT": Decimal("800")},
    )
    # 先讓 B 預留 600
    ledger.apply(_reservation(strategy_id="B", symbol="BTCUSDT", notional=Decimal("600")))
    # A 想預留 500：strategy 800 OK，symbol 200 (800-600) 不夠
    result = ledger.check(strategy_id="A", symbol="BTCUSDT", notional=Decimal("500"))
    assert result.ok is False
    assert result.reason == "symbol_concentration_insufficient"


def test_check_unknown_symbol_treats_as_unlimited() -> None:
    """未列入 symbol_caps 的標的：視為無限額（讓 strategy/global 守關）。"""
    ledger = _ledger()
    result = ledger.check(strategy_id="A", symbol="SOLUSDT", notional=Decimal("500"))
    assert result.ok is True


# ===== apply / revert =====


def test_apply_updates_three_layers() -> None:
    ledger = _ledger()
    ledger.apply(_reservation(notional=Decimal("1000")))
    assert ledger.strategy_available("A") == Decimal("4000")
    assert ledger.symbol_available("BTCUSDT") == Decimal("3000")
    assert ledger.total_reserved == Decimal("1000")
    assert ledger.total_free == Decimal("9000")


def test_apply_duplicate_id_raises() -> None:
    ledger = _ledger()
    res = _reservation()
    ledger.apply(res)
    with pytest.raises(ValueError, match="duplicate"):
        ledger.apply(res)


def test_revert_releases_capacity() -> None:
    ledger = _ledger()
    res = _reservation(notional=Decimal("1000"))
    ledger.apply(res)
    reverted = ledger.revert(res.reservation_id)
    assert reverted is not None
    assert reverted.reservation_id == res.reservation_id
    assert ledger.strategy_available("A") == Decimal("5000")
    assert ledger.symbol_available("BTCUSDT") == Decimal("4000")
    assert ledger.total_reserved == Decimal("0")


def test_revert_unknown_id_returns_none() -> None:
    """spec scenario：重複釋放冪等（未知 id 為 no-op）。"""
    ledger = _ledger()
    result = ledger.revert(uuid4())
    assert result is None


def test_revert_already_reverted_returns_none() -> None:
    ledger = _ledger()
    res = _reservation()
    ledger.apply(res)
    ledger.revert(res.reservation_id)
    second = ledger.revert(res.reservation_id)
    assert second is None
    # ledger 數值仍正確
    assert ledger.total_reserved == Decimal("0")


def test_has_reservation() -> None:
    ledger = _ledger()
    res = _reservation()
    assert ledger.has_reservation(res.reservation_id) is False
    ledger.apply(res)
    assert ledger.has_reservation(res.reservation_id) is True
    ledger.revert(res.reservation_id)
    assert ledger.has_reservation(res.reservation_id) is False
