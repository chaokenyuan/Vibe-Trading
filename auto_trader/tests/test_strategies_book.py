"""LogicalBook 測試。"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from risk.types import Side
from strategies.book import LogicalBook
from strategies.types import Fill


def _fill(
    *,
    side: Side = Side.BUY,
    qty: Decimal = Decimal("1"),
    price: Decimal = Decimal("65000"),
    symbol: str = "BTCUSDT",
) -> Fill:
    return Fill(
        fill_id=uuid4(),
        client_order_id="A.abc.1",
        broker_order_id="bo",
        symbol=symbol,
        side=side,
        qty=qty,
        price=price,
        fees=Decimal("0"),
        at=datetime(2026, 5, 10, tzinfo=UTC),
    )


def test_open_position_from_empty_book() -> None:
    book = LogicalBook(strategy_id="A")
    book.apply_fill(_fill(side=Side.BUY, qty=Decimal("1"), price=Decimal("65000")))
    pos = book.get_position("BTCUSDT")
    assert pos is not None
    assert pos.qty == Decimal("1")
    assert pos.avg_entry == Decimal("65000")


def test_add_to_existing_long_updates_avg_entry() -> None:
    book = LogicalBook(strategy_id="A")
    book.apply_fill(_fill(side=Side.BUY, qty=Decimal("1"), price=Decimal("65000")))
    book.apply_fill(_fill(side=Side.BUY, qty=Decimal("1"), price=Decimal("67000")))
    pos = book.get_position("BTCUSDT")
    assert pos is not None
    assert pos.qty == Decimal("2")
    assert pos.avg_entry == Decimal("66000")


def test_close_long_position_removes_entry() -> None:
    book = LogicalBook(strategy_id="A")
    book.apply_fill(_fill(side=Side.BUY, qty=Decimal("1")))
    book.apply_fill(_fill(side=Side.SELL, qty=Decimal("1")))
    assert book.get_position("BTCUSDT") is None
    assert book.total_position_count() == 0


def test_open_short_position() -> None:
    book = LogicalBook(strategy_id="A")
    book.apply_fill(_fill(side=Side.SELL, qty=Decimal("1"), price=Decimal("65000")))
    pos = book.get_position("BTCUSDT")
    assert pos is not None
    assert pos.qty == Decimal("-1")


def test_partial_reduction_keeps_position() -> None:
    book = LogicalBook(strategy_id="A")
    book.apply_fill(_fill(side=Side.BUY, qty=Decimal("2"), price=Decimal("65000")))
    book.apply_fill(_fill(side=Side.SELL, qty=Decimal("1"), price=Decimal("70000")))
    pos = book.get_position("BTCUSDT")
    assert pos is not None
    assert pos.qty == Decimal("1")
    # avg_entry 保留原值（pnl 計算屬 reconciliation）
    assert pos.avg_entry == Decimal("65000")


def test_distinct_symbols_isolated() -> None:
    book = LogicalBook(strategy_id="A")
    book.apply_fill(_fill(symbol="BTCUSDT", qty=Decimal("1")))
    book.apply_fill(_fill(symbol="ETHUSDT", qty=Decimal("10"), price=Decimal("3000")))
    btc = book.get_position("BTCUSDT")
    eth = book.get_position("ETHUSDT")
    assert btc is not None and eth is not None
    assert btc.qty == Decimal("1")
    assert eth.qty == Decimal("10")
    assert book.total_position_count() == 2


def test_list_positions() -> None:
    book = LogicalBook(strategy_id="A")
    book.apply_fill(_fill(symbol="BTCUSDT"))
    book.apply_fill(_fill(symbol="ETHUSDT", price=Decimal("3000")))
    positions = book.list_positions()
    symbols = sorted(p.symbol for p in positions)
    assert symbols == ["BTCUSDT", "ETHUSDT"]


def test_strategy_id_property() -> None:
    book = LogicalBook(strategy_id="vibe_btc_v1")
    assert book.strategy_id == "vibe_btc_v1"
