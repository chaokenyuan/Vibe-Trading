"""ReservationBridge 測試。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from execution.events import OrderRejectedByBroker, OrderSubmitted
from reconciliation.events import FillProcessed
from reservation_bridge.bridge import ReservationBridge
from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.reservation.ledger import ReservationLedger
from risk.reservation.reserver import CapitalReserver
from risk.types import OrderIntent, Side
from tests.fakes.frozen_clock import FrozenClock


def _intent(strategy_id: str = "A") -> OrderIntent:
    return OrderIntent(
        strategy_id=strategy_id,
        symbol="BTCUSDT",
        side=Side.BUY,
        qty=Decimal("1"),
        price=Decimal("65000"),
        signal_id="sig",
        bar_time=datetime(2026, 5, 10, tzinfo=UTC),
        received_at=datetime(2026, 5, 10, 0, 0, 1, tzinfo=UTC),
    )


def _setup() -> tuple[
    ReservationBridge,
    InMemoryEventPublisher,
    CapitalReserver,
    ReservationLedger,
    FrozenClock,
]:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    publisher = InMemoryEventPublisher()
    ledger = ReservationLedger(
        total_equity=Decimal("100000"),
        strategy_budgets={"A": Decimal("100000")},
        symbol_caps={"BTCUSDT": Decimal("100000")},
    )
    reserver = CapitalReserver(ledger=ledger, clock=clock, publisher=publisher)
    bridge = ReservationBridge(
        publisher=publisher,
        reserver=reserver,
        clock=clock,
    )
    bridge.start()
    return bridge, publisher, reserver, ledger, clock


# ===== OrderSubmitted 紀錄 mapping =====


@pytest.mark.asyncio
async def test_order_submitted_records_mapping() -> None:
    """spec scenario：OrderSubmitted 紀錄 mapping。"""
    bridge, publisher, _, _, _ = _setup()
    rid = uuid4()

    await publisher.publish(
        OrderSubmitted(
            at=datetime(2026, 5, 10, tzinfo=UTC),
            client_order_id="A.x.1",
            broker_order_id="bo-1",
            symbol="BTCUSDT",
            strategy_id="A",
            reservation_id=rid,
        )
    )

    assert bridge.mapping_size == 1


@pytest.mark.asyncio
async def test_order_submitted_with_none_reservation_skipped() -> None:
    """spec scenario：OrderSubmitted reservation_id 為 None 時跳過。"""
    bridge, publisher, _, _, _ = _setup()

    await publisher.publish(
        OrderSubmitted(
            at=datetime(2026, 5, 10, tzinfo=UTC),
            client_order_id="A.x.1",
            broker_order_id="bo-1",
            symbol="BTCUSDT",
            strategy_id="A",
            reservation_id=None,
        )
    )

    assert bridge.mapping_size == 0


# ===== OrderRejectedByBroker 釋放 =====


@pytest.mark.asyncio
async def test_order_rejected_releases_reservation() -> None:
    """spec scenario：OrderRejectedByBroker 釋放 reservation。"""
    bridge, publisher, reserver, ledger, clock = _setup()

    # 先預留實際 reservation
    await reserver.start()
    try:
        result = await reserver.reserve(intent=_intent(), notional=Decimal("1000"))
    finally:
        # 暫停 reserver；但仍可呼叫 release（內部 actor 處理 queue）
        pass

    assert result.reservation_id is not None
    rid: UUID = result.reservation_id

    # 模擬 OrderSubmitted 紀錄 mapping
    await publisher.publish(
        OrderSubmitted(
            at=clock.now(),
            client_order_id="A.x.1",
            broker_order_id="bo-1",
            symbol="BTCUSDT",
            strategy_id="A",
            reservation_id=rid,
        )
    )
    assert ledger.total_reserved == Decimal("1000")

    # 模擬 broker 拒單
    await publisher.publish(
        OrderRejectedByBroker(
            at=clock.now(),
            client_order_id="A.x.1",
            symbol="BTCUSDT",
            strategy_id="A",
            reason="balance",
        )
    )

    # mapping 中 C1 已移除
    assert bridge.mapping_size == 0
    # ledger 已釋放
    assert ledger.total_reserved == Decimal("0")

    await reserver.stop()


# ===== FillProcessed 釋放 =====


@pytest.mark.asyncio
async def test_fill_processed_releases_reservation() -> None:
    """spec scenario：FillProcessed 釋放 reservation。"""
    bridge, publisher, reserver, ledger, clock = _setup()
    await reserver.start()
    result = await reserver.reserve(intent=_intent(), notional=Decimal("500"))

    assert result.reservation_id is not None
    rid = result.reservation_id

    await publisher.publish(
        OrderSubmitted(
            at=clock.now(),
            client_order_id="A.fill.1",
            broker_order_id="bo-2",
            symbol="BTCUSDT",
            strategy_id="A",
            reservation_id=rid,
        )
    )
    assert ledger.total_reserved == Decimal("500")

    await publisher.publish(
        FillProcessed(
            at=clock.now(),
            fill_id=str(uuid4()),
            client_order_id="A.fill.1",
            strategy_id="A",
            symbol="BTCUSDT",
        )
    )

    assert bridge.mapping_size == 0
    assert ledger.total_reserved == Decimal("0")
    await reserver.stop()


# ===== 未知 client_order_id =====


@pytest.mark.asyncio
async def test_unknown_client_order_id_does_not_release(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """spec scenario：未知 client_order_id 的 fill 不釋放。"""
    _bridge, publisher, _reserver, ledger, clock = _setup()

    with caplog.at_level(logging.WARNING):
        await publisher.publish(
            FillProcessed(
                at=clock.now(),
                fill_id=str(uuid4()),
                client_order_id="UNKNOWN.x.1",
                strategy_id="X",
                symbol="BTCUSDT",
            )
        )

    assert ledger.total_reserved == Decimal("0")
    assert any("no reservation mapping" in r.message for r in caplog.records)


# ===== release 失敗容錯 =====


@pytest.mark.asyncio
async def test_release_failure_logged_but_not_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """spec scenario：release 失敗紀錄 error 但不向上拋。"""

    class _FailingReserver:
        async def release(self, rid: UUID) -> None:
            raise RuntimeError("intentional failure")

    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    publisher = InMemoryEventPublisher()
    bridge = ReservationBridge(
        publisher=publisher,
        reserver=_FailingReserver(),  # type: ignore[arg-type]
        clock=clock,
    )
    bridge.start()

    rid = uuid4()
    await publisher.publish(
        OrderSubmitted(
            at=clock.now(),
            client_order_id="A.x.1",
            broker_order_id="bo",
            symbol="BTCUSDT",
            strategy_id="A",
            reservation_id=rid,
        )
    )

    with caplog.at_level(logging.ERROR):
        # 不應拋例外
        await publisher.publish(
            FillProcessed(
                at=clock.now(),
                fill_id=str(uuid4()),
                client_order_id="A.x.1",
                strategy_id="A",
                symbol="BTCUSDT",
            )
        )

    assert any("reserver.release failed" in r.message for r in caplog.records)


# ===== LRU 淘汰 =====


@pytest.mark.asyncio
async def test_mapping_lru_eviction() -> None:
    """spec scenario：mapping 達上限觸發 LRU 淘汰。"""
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    publisher = InMemoryEventPublisher()

    class _NoOpReserver:
        async def release(self, rid: UUID) -> None:
            pass

    bridge = ReservationBridge(
        publisher=publisher,
        reserver=_NoOpReserver(),  # type: ignore[arg-type]
        clock=clock,
        max_entries=3,
    )
    bridge.start()

    for i in range(5):
        await publisher.publish(
            OrderSubmitted(
                at=clock.now(),
                client_order_id=f"A.x.{i}",
                broker_order_id=f"bo-{i}",
                symbol="BTCUSDT",
                strategy_id="A",
                reservation_id=uuid4(),
            )
        )

    assert bridge.mapping_size == 3


# ===== TTL 過期 =====


@pytest.mark.asyncio
async def test_expired_mapping_not_released() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    publisher = InMemoryEventPublisher()
    released: list[UUID] = []

    class _RecordingReserver:
        async def release(self, rid: UUID) -> None:
            released.append(rid)

    bridge = ReservationBridge(
        publisher=publisher,
        reserver=_RecordingReserver(),  # type: ignore[arg-type]
        clock=clock,
        ttl_seconds=10,
    )
    bridge.start()

    rid = uuid4()
    await publisher.publish(
        OrderSubmitted(
            at=clock.now(),
            client_order_id="A.x.1",
            broker_order_id="bo",
            symbol="BTCUSDT",
            strategy_id="A",
            reservation_id=rid,
        )
    )

    # 過 TTL
    clock.advance(timedelta(seconds=11))

    await publisher.publish(
        FillProcessed(
            at=clock.now(),
            fill_id=str(uuid4()),
            client_order_id="A.x.1",
            strategy_id="A",
            symbol="BTCUSDT",
        )
    )

    # 不應釋放（已過期）
    assert released == []
    # 過期條目移除
    assert bridge.mapping_size == 0
