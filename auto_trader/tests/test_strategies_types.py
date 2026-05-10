"""StrategyState / LogicalPosition / Fill 測試。"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from risk.types import Side
from strategies.types import Fill, LogicalPosition, StrategyState


def test_strategy_state_has_six_values() -> None:
    assert len(list(StrategyState)) == 6
    assert StrategyState.LOADED.value == "LOADED"
    assert StrategyState.FAILED.value == "FAILED"


def test_logical_position_immutable() -> None:
    p = LogicalPosition(
        strategy_id="A",
        symbol="BTCUSDT",
        qty=Decimal("1"),
        avg_entry=Decimal("65000"),
        opened_at=datetime(2026, 5, 10, tzinfo=UTC),
        open_signal_id="sig",
    )
    with pytest.raises(FrozenInstanceError):
        p.qty = Decimal("2")  # type: ignore[misc]


def test_logical_position_serializable() -> None:
    p = LogicalPosition(
        strategy_id="A",
        symbol="BTCUSDT",
        qty=Decimal("1"),
        avg_entry=Decimal("65000"),
        opened_at=datetime(2026, 5, 10, tzinfo=UTC),
        open_signal_id="sig",
    )
    encoded = json.dumps(p.to_dict())
    decoded = json.loads(encoded)
    assert decoded["qty"] == "1"
    assert decoded["avg_entry"] == "65000"


def test_fill_immutable() -> None:
    f = Fill(
        fill_id=uuid4(),
        client_order_id="A.abc.1",
        broker_order_id="bo-123",
        symbol="BTCUSDT",
        side=Side.BUY,
        qty=Decimal("1"),
        price=Decimal("65000"),
        fees=Decimal("0.5"),
        at=datetime(2026, 5, 10, tzinfo=UTC),
    )
    with pytest.raises(FrozenInstanceError):
        f.qty = Decimal("2")  # type: ignore[misc]


def test_fill_serializable() -> None:
    fid = uuid4()
    f = Fill(
        fill_id=fid,
        client_order_id="A.abc.1",
        broker_order_id="bo-123",
        symbol="BTCUSDT",
        side=Side.BUY,
        qty=Decimal("1"),
        price=Decimal("65000"),
        fees=Decimal("0.5"),
        at=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC),
    )
    encoded = json.dumps(f.to_dict())
    decoded = json.loads(encoded)
    assert decoded["fill_id"] == str(fid)
    assert decoded["side"] == "BUY"
    assert decoded["fees"] == "0.5"
    assert decoded["at"] == "2026-05-10T12:00:00+00:00"
