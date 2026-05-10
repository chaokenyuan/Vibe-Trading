"""Signal / StrategyMetadata 不可變性與序列化測試。"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from signals.types import (
    SCHEMA_VERSION_CURRENT,
    Signal,
    SignalSourceKind,
    StrategyMetadata,
)


def _signal() -> Signal:
    return Signal(
        schema_version=SCHEMA_VERSION_CURRENT,
        signal_id="abc123",
        strategy_id="vibe_btc_v1",
        strategy_version="1.0.0",
        params_hash="hash",
        symbol="BTCUSDT",
        side="BUY",
        qty=Decimal("1"),
        price=Decimal("65000"),
        bar_time=datetime(2026, 5, 10, tzinfo=UTC),
        interval="60",
        received_at=datetime(2026, 5, 10, 0, 0, 1, tzinfo=UTC),
        source=SignalSourceKind.TRADINGVIEW,
        comment=None,
        raw_payload={"v": 1, "strategy_id": "vibe_btc_v1"},
    )


def test_signal_immutable() -> None:
    s = _signal()
    with pytest.raises(FrozenInstanceError):
        s.qty = Decimal("2")  # type: ignore[misc]


def test_signal_to_dict_json_serializable() -> None:
    s = _signal()
    encoded = json.dumps(s.to_dict())
    decoded = json.loads(encoded)
    assert decoded["signal_id"] == "abc123"
    assert decoded["qty"] == "1"
    assert decoded["price"] == "65000"
    assert decoded["bar_time"] == "2026-05-10T00:00:00+00:00"
    assert decoded["source"] == "tradingview"
    assert decoded["raw_payload"]["v"] == 1


def test_strategy_metadata_immutable() -> None:
    m = StrategyMetadata(
        strategy_id="A", strategy_version="1.0.0", params_hash="abc"
    )
    with pytest.raises(FrozenInstanceError):
        m.strategy_version = "2.0.0"  # type: ignore[misc]


def test_signal_source_kind_values() -> None:
    assert SignalSourceKind.TRADINGVIEW.value == "tradingview"
    assert SignalSourceKind.MT5.value == "mt5"
    assert SignalSourceKind.VIBE_SHADOW.value == "vibe_shadow"
    assert SignalSourceKind.MANUAL.value == "manual"


def test_signal_with_none_price_serializes() -> None:
    s = _signal()
    s2 = Signal(
        schema_version=s.schema_version,
        signal_id=s.signal_id,
        strategy_id=s.strategy_id,
        strategy_version=s.strategy_version,
        params_hash=s.params_hash,
        symbol=s.symbol,
        side=s.side,
        qty=s.qty,
        price=None,
        bar_time=s.bar_time,
        interval=s.interval,
        received_at=s.received_at,
        source=s.source,
        comment=s.comment,
        raw_payload=s.raw_payload,
    )
    encoded = json.dumps(s2.to_dict())
    decoded = json.loads(encoded)
    assert decoded["price"] is None
