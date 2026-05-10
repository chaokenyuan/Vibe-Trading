"""通用值物件序列化與不可變性測試。

對應 spec：所有值物件 SHALL 為 frozen dataclass。
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, asdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from risk.types import OrderIntent, Position, ReservationResult, Side


def test_order_intent_immutable() -> None:
    oi = OrderIntent(
        strategy_id="vibe_btc_v1",
        symbol="BTCUSDT",
        side=Side.BUY,
        qty=Decimal("1"),
        price=None,
        signal_id="sig_abc",
        bar_time=datetime(2026, 5, 10, tzinfo=UTC),
        received_at=datetime(2026, 5, 10, 0, 0, 1, tzinfo=UTC),
    )
    with pytest.raises(FrozenInstanceError):
        oi.qty = Decimal("2")  # type: ignore[misc]


def test_order_intent_asdict_roundtrip() -> None:
    oi = OrderIntent(
        strategy_id="A",
        symbol="BTCUSDT",
        side=Side.BUY,
        qty=Decimal("1"),
        price=Decimal("65000"),
        signal_id="sig",
        bar_time=datetime(2026, 5, 10, tzinfo=UTC),
        received_at=datetime(2026, 5, 10, 0, 0, 1, tzinfo=UTC),
    )
    d = asdict(oi)
    assert d["strategy_id"] == "A"
    assert d["side"] == "BUY"
    # Decimal 與 datetime 在 asdict 中保持原型，需正規化才能 json.dumps
    # 此處測試 asdict 的結構正確性


def test_position_immutable() -> None:
    p = Position(
        strategy_id="A",
        symbol="BTCUSDT",
        qty=Decimal("1"),
        avg_entry=Decimal("65000"),
        opened_at=datetime(2026, 5, 10, tzinfo=UTC),
    )
    with pytest.raises(FrozenInstanceError):
        p.qty = Decimal("2")  # type: ignore[misc]


def test_position_short() -> None:
    """qty 負值代表 short。"""
    p = Position(
        strategy_id="A",
        symbol="BTCUSDT",
        qty=Decimal("-0.5"),
        avg_entry=Decimal("65200"),
        opened_at=datetime(2026, 5, 10, tzinfo=UTC),
    )
    assert p.qty < 0


def test_reservation_result_success_shape() -> None:
    rid = uuid4()
    rr = ReservationResult(ok=True, reservation_id=rid, reason=None, available=None)
    assert rr.ok is True
    assert rr.reservation_id == rid
    assert rr.reason is None


def test_reservation_result_failure_shape() -> None:
    rr = ReservationResult(
        ok=False,
        reservation_id=None,
        reason="symbol_concentration_insufficient",
        available=Decimal("500"),
    )
    assert rr.ok is False
    assert rr.reason == "symbol_concentration_insufficient"
    assert rr.available == Decimal("500")


def test_side_str_enum_values() -> None:
    assert Side.BUY.value == "BUY"
    assert Side.SELL.value == "SELL"
    assert Side.CLOSE.value == "CLOSE"


def test_value_objects_json_compatible_via_normalize() -> None:
    """通用測試：所有值物件 asdict 後可透過正規化 json.dumps。

    正規化策略與 risk.decision._normalize 一致：
    Decimal->str, UUID->str, datetime->isoformat, StrEnum->.value
    """
    oi = OrderIntent(
        strategy_id="A",
        symbol="BTCUSDT",
        side=Side.BUY,
        qty=Decimal("1"),
        price=None,
        signal_id="sig",
        bar_time=datetime(2026, 5, 10, tzinfo=UTC),
        received_at=datetime(2026, 5, 10, 0, 0, 1, tzinfo=UTC),
    )
    d = asdict(oi)
    normalized = _to_json_safe(d)
    encoded = json.dumps(normalized)
    decoded = json.loads(encoded)
    assert decoded["strategy_id"] == "A"
    assert decoded["qty"] == "1"
    assert decoded["bar_time"] == "2026-05-10T00:00:00+00:00"


def _to_json_safe(obj: object) -> object:
    """測試輔助：與 risk.decision._normalize 等效的最小實作。"""
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_json_safe(x) for x in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj
