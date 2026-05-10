"""Event 基底與具體事件型別測試 + InMemoryEventPublisher 測試。

對應 spec scenario：
- 每筆 Decision 觸發一個事件
- KILL_SWITCH 同時觸發兩個事件（透過具體事件型別表達）
- 事件可序列化供 SQLite event log
- 訂閱者間無耦合（一個失敗其他繼續）
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest

from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.decision import Decision, Verdict
from risk.events import (
    ConfigLoaded,
    DailyPnlReset,
    DecisionEmitted,
    EmergencyFlattenRequested,
    Event,
    ReservationCreated,
    ReservationReleased,
    StateChanged,
)

# ===== Event 基底測試 =====


def test_event_default_event_id_is_uuid() -> None:
    e = Event(at=datetime(2026, 5, 10, tzinfo=UTC))
    assert isinstance(e.event_id, UUID)


def test_event_unique_default_event_id() -> None:
    e1 = Event(at=datetime(2026, 5, 10, tzinfo=UTC))
    e2 = Event(at=datetime(2026, 5, 10, tzinfo=UTC))
    assert e1.event_id != e2.event_id


def test_event_kw_only_rejects_positional() -> None:
    with pytest.raises(TypeError):
        Event(datetime(2026, 5, 10, tzinfo=UTC))  # type: ignore[misc]


def test_event_immutable() -> None:
    e = Event(at=datetime(2026, 5, 10, tzinfo=UTC))
    with pytest.raises(FrozenInstanceError):
        e.at = datetime(2026, 5, 11, tzinfo=UTC)  # type: ignore[misc]


def test_event_to_dict_serializable() -> None:
    e = Event(at=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC))
    payload = e.to_dict()
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded["at"] == "2026-05-10T12:00:00+00:00"
    assert UUID(decoded["event_id"])  # 可解析回 UUID


# ===== 具體事件型別測試 =====


def test_state_changed_event() -> None:
    e = StateChanged(
        at=datetime(2026, 5, 10, tzinfo=UTC),
        from_state="NORMAL",
        to_state="WARNING",
        reason="daily_pnl=-2.3%",
    )
    payload = e.to_dict()
    assert payload["from_state"] == "NORMAL"
    assert payload["to_state"] == "WARNING"


def test_decision_emitted_event_serializable() -> None:
    """spec scenario: 每筆 Decision 觸發一個事件 + 完整 Decision 序列化。"""
    decision = Decision(
        verdict=Verdict.APPROVE,
        final_size=Decimal("5"),
        final_price=None,
        reasons=[],
        reservation_id=None,
        evaluated_at=datetime(2026, 5, 10, tzinfo=UTC),
    )
    e = DecisionEmitted(at=datetime(2026, 5, 10, tzinfo=UTC), decision=decision)
    payload = e.to_dict()
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded["decision"]["verdict"] == "APPROVE"
    assert decoded["decision"]["final_size"] == "5"


def test_reservation_created_event() -> None:
    rid = uuid4()
    e = ReservationCreated(
        at=datetime(2026, 5, 10, tzinfo=UTC),
        reservation_id=rid,
        strategy_id="A",
        symbol="BTCUSDT",
        qty=Decimal("1"),
    )
    payload = e.to_dict()
    assert payload["reservation_id"] == str(rid)
    assert payload["qty"] == "1"


def test_reservation_released_event() -> None:
    rid = uuid4()
    e = ReservationReleased(at=datetime(2026, 5, 10, tzinfo=UTC), reservation_id=rid)
    assert e.reservation_id == rid


def test_config_loaded_event() -> None:
    e = ConfigLoaded(at=datetime(2026, 5, 10, tzinfo=UTC), params_hash="abc123")
    assert e.params_hash == "abc123"


def test_emergency_flatten_requested_event() -> None:
    e = EmergencyFlattenRequested(at=datetime(2026, 5, 10, tzinfo=UTC))
    assert isinstance(e.event_id, UUID)


def test_daily_pnl_reset_event() -> None:
    e = DailyPnlReset(at=datetime(2026, 5, 10, tzinfo=UTC))
    assert isinstance(e.event_id, UUID)


# ===== InMemoryEventPublisher 測試 =====


@pytest.mark.asyncio
async def test_subscribe_specific_type_receives() -> None:
    pub = InMemoryEventPublisher()
    received: list[StateChanged] = []

    async def handler(e: StateChanged) -> None:
        received.append(e)

    pub.subscribe(StateChanged, handler)
    event = StateChanged(
        at=datetime(2026, 5, 10, tzinfo=UTC),
        from_state="NORMAL",
        to_state="WARNING",
        reason="test",
    )
    await pub.publish(event)
    assert len(received) == 1
    assert received[0] is event


@pytest.mark.asyncio
async def test_subscribe_event_base_receives_all() -> None:
    """訂閱 Event 基底等於訂閱所有事件型別。"""
    pub = InMemoryEventPublisher()
    received: list[Event] = []

    async def audit_handler(e: Event) -> None:
        received.append(e)

    pub.subscribe(Event, audit_handler)

    await pub.publish(StateChanged(
        at=datetime(2026, 5, 10, tzinfo=UTC),
        from_state="A", to_state="B", reason="x",
    ))
    await pub.publish(EmergencyFlattenRequested(at=datetime(2026, 5, 10, tzinfo=UTC)))
    await pub.publish(ConfigLoaded(at=datetime(2026, 5, 10, tzinfo=UTC), params_hash="h"))

    assert len(received) == 3


@pytest.mark.asyncio
async def test_specific_type_does_not_receive_other_types() -> None:
    pub = InMemoryEventPublisher()
    received: list[StateChanged] = []

    async def handler(e: StateChanged) -> None:
        received.append(e)

    pub.subscribe(StateChanged, handler)
    await pub.publish(EmergencyFlattenRequested(at=datetime(2026, 5, 10, tzinfo=UTC)))
    assert received == []


@pytest.mark.asyncio
async def test_multiple_subscribers_all_receive() -> None:
    pub = InMemoryEventPublisher()
    a_received: list[Event] = []
    b_received: list[Event] = []

    async def a(e: StateChanged) -> None:
        a_received.append(e)

    async def b(e: StateChanged) -> None:
        b_received.append(e)

    pub.subscribe(StateChanged, a)
    pub.subscribe(StateChanged, b)
    event = StateChanged(at=datetime(2026, 5, 10, tzinfo=UTC),
                         from_state="A", to_state="B", reason="x")
    await pub.publish(event)
    assert len(a_received) == 1
    assert len(b_received) == 1


@pytest.mark.asyncio
async def test_failing_subscriber_does_not_break_others() -> None:
    """spec scenario：訂閱者間無耦合（一個失敗其他繼續）。"""
    pub = InMemoryEventPublisher()
    succeeded: list[Event] = []

    async def failing(e: StateChanged) -> None:
        raise RuntimeError("intentional failure")

    async def succeeding(e: StateChanged) -> None:
        succeeded.append(e)

    pub.subscribe(StateChanged, failing)
    pub.subscribe(StateChanged, succeeding)

    event = StateChanged(at=datetime(2026, 5, 10, tzinfo=UTC),
                         from_state="A", to_state="B", reason="x")
    # 不應拋例外
    await pub.publish(event)
    assert len(succeeded) == 1


@pytest.mark.asyncio
async def test_publish_with_no_subscribers_is_noop() -> None:
    pub = InMemoryEventPublisher()
    await pub.publish(EmergencyFlattenRequested(at=datetime(2026, 5, 10, tzinfo=UTC)))
    # 無 handler 也不應拋


@pytest.mark.asyncio
async def test_event_serialization_roundtrip_via_publisher() -> None:
    """spec scenario：事件可序列化供 SQLite event log。"""
    pub = InMemoryEventPublisher()
    captured: list[dict[str, object]] = []

    async def store_handler(e: Event) -> None:
        captured.append(e.to_dict())

    pub.subscribe(Event, store_handler)

    rid = uuid4()
    await pub.publish(ReservationCreated(
        at=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC),
        reservation_id=rid,
        strategy_id="A",
        symbol="BTCUSDT",
        qty=Decimal("1.5"),
    ))

    encoded = json.dumps(captured[0])
    decoded = cast(dict[str, object], json.loads(encoded))
    assert decoded["strategy_id"] == "A"
    assert decoded["qty"] == "1.5"
    assert decoded["reservation_id"] == str(rid)


@pytest.mark.asyncio
async def test_publisher_satisfies_protocol() -> None:
    """InMemoryEventPublisher 結構性符合 EventPublisher Protocol。"""
    from risk.ports import EventPublisher

    pub = InMemoryEventPublisher()
    assert isinstance(pub, EventPublisher)
