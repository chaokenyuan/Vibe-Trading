"""CapitalReserver actor 單元 + 並發測試。

對應 spec scenario：
- 三道全通過則成功預留
- 任一不足則拒（per-strategy / per-symbol / global）
- FCFS 順序保證
- 釋放預留歸還額度
- 重複釋放冪等
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.events import Event, ReservationCreated, ReservationReleased
from risk.reservation.ledger import ReservationLedger
from risk.reservation.reserver import CapitalReserver
from risk.types import OrderIntent, Side
from tests.fakes.frozen_clock import FrozenClock


def _intent(
    strategy_id: str = "A",
    symbol: str = "BTCUSDT",
    qty: Decimal = Decimal("1"),
) -> OrderIntent:
    return OrderIntent(
        strategy_id=strategy_id,
        symbol=symbol,
        side=Side.BUY,
        qty=qty,
        price=Decimal("65000"),
        signal_id=f"sig_{strategy_id}_{symbol}",
        bar_time=datetime(2026, 5, 10, tzinfo=UTC),
        received_at=datetime(2026, 5, 10, 0, 0, 1, tzinfo=UTC),
    )


def _make_reserver() -> tuple[CapitalReserver, ReservationLedger, list[Event]]:
    ledger = ReservationLedger(
        total_equity=Decimal("10000"),
        strategy_budgets={"A": Decimal("5000"), "B": Decimal("4000")},
        symbol_caps={"BTCUSDT": Decimal("4000")},
    )
    publisher = InMemoryEventPublisher()
    received: list[Event] = []

    async def capture(e: Event) -> None:
        received.append(e)

    publisher.subscribe(Event, capture)

    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    reserver = CapitalReserver(ledger=ledger, clock=clock, publisher=publisher)
    return reserver, ledger, received


# ===== 基本 reserve / release =====


@pytest.mark.asyncio
async def test_reserve_success_updates_ledger_and_emits_event() -> None:
    reserver, ledger, received = _make_reserver()
    await reserver.start()
    try:
        result = await reserver.reserve(intent=_intent(), notional=Decimal("1000"))
    finally:
        await reserver.stop()

    assert result.ok is True
    assert result.reservation_id is not None
    assert ledger.strategy_available("A") == Decimal("4000")
    assert ledger.symbol_available("BTCUSDT") == Decimal("3000")
    assert ledger.total_free == Decimal("9000")

    created = [e for e in received if isinstance(e, ReservationCreated)]
    assert len(created) == 1
    assert created[0].reservation_id == result.reservation_id


@pytest.mark.asyncio
async def test_reserve_strategy_insufficient_returns_failure() -> None:
    reserver, _, _ = _make_reserver()
    await reserver.start()
    try:
        result = await reserver.reserve(intent=_intent(), notional=Decimal("6000"))
    finally:
        await reserver.stop()
    assert result.ok is False
    assert result.reason == "strategy_budget_insufficient"
    assert result.available == Decimal("5000")


@pytest.mark.asyncio
async def test_reserve_symbol_insufficient_returns_failure() -> None:
    """spec scenario：symbol 集中度不足時拒，回傳 reason 與 available。"""
    big = ReservationLedger(
        total_equity=Decimal("100000"),
        strategy_budgets={"A": Decimal("50000")},
        symbol_caps={"BTCUSDT": Decimal("4000")},
    )
    publisher = InMemoryEventPublisher()
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    reserver = CapitalReserver(ledger=big, clock=clock, publisher=publisher)

    await reserver.start()
    try:
        result = await reserver.reserve(intent=_intent(), notional=Decimal("4500"))
    finally:
        await reserver.stop()
    assert result.ok is False
    assert result.reason == "symbol_concentration_insufficient"
    assert result.available == Decimal("4000")


@pytest.mark.asyncio
async def test_release_returns_capacity_and_emits_event() -> None:
    """spec scenario：釋放預留歸還額度。"""
    reserver, ledger, received = _make_reserver()
    await reserver.start()
    try:
        result = await reserver.reserve(intent=_intent(), notional=Decimal("1000"))
        assert result.reservation_id is not None
        await reserver.release(result.reservation_id)
    finally:
        await reserver.stop()

    assert ledger.strategy_available("A") == Decimal("5000")
    assert ledger.symbol_available("BTCUSDT") == Decimal("4000")
    assert ledger.total_reserved == Decimal("0")

    released = [e for e in received if isinstance(e, ReservationReleased)]
    assert len(released) == 1
    assert released[0].reservation_id == result.reservation_id


@pytest.mark.asyncio
async def test_release_idempotent_on_duplicate_call() -> None:
    """spec scenario：重複釋放冪等（不拋例外、不重複歸還）。"""
    reserver, ledger, received = _make_reserver()
    await reserver.start()
    try:
        result = await reserver.reserve(intent=_intent(), notional=Decimal("1000"))
        assert result.reservation_id is not None
        await reserver.release(result.reservation_id)
        await reserver.release(result.reservation_id)  # 第二次：no-op
    finally:
        await reserver.stop()

    # ledger 仍正確
    assert ledger.total_reserved == Decimal("0")
    # 只發一個 ReservationReleased 事件
    released = [e for e in received if isinstance(e, ReservationReleased)]
    assert len(released) == 1


@pytest.mark.asyncio
async def test_release_unknown_id_is_noop() -> None:
    from uuid import uuid4

    reserver, ledger, received = _make_reserver()
    await reserver.start()
    try:
        await reserver.release(uuid4())
    finally:
        await reserver.stop()

    # 無事件、ledger 不變
    assert ledger.total_reserved == Decimal("0")
    released = [e for e in received if isinstance(e, ReservationReleased)]
    assert released == []


# ===== FCFS 並發 =====


@pytest.mark.asyncio
async def test_fcfs_concurrent_reservations_consistent_ledger() -> None:
    """spec scenario：FCFS 並發 100 請求，ledger 一致性。

    每個請求 100 notional，總共 100 個 = 10000 但池子也是 10000，
    且 strategy A 預算 5000、B 預算 4000，symbol BTC 4000。
    結合三道限制驗證最終一致性：成功筆數 = min(strategy/symbol/global)。
    """
    ledger = ReservationLedger(
        total_equity=Decimal("10000"),
        strategy_budgets={"A": Decimal("5000")},
        symbol_caps={"BTCUSDT": Decimal("4000")},
    )
    publisher = InMemoryEventPublisher()
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    reserver = CapitalReserver(ledger=ledger, clock=clock, publisher=publisher)

    await reserver.start()
    try:
        # 100 個請求，每個 notional=100，A 策略 BTC 標的
        tasks = [
            reserver.reserve(intent=_intent(), notional=Decimal("100"))
            for _ in range(100)
        ]
        results = await asyncio.gather(*tasks)
    finally:
        await reserver.stop()

    successes = [r for r in results if r.ok]
    failures = [r for r in results if not r.ok]

    # symbol BTC 上限 4000 / 每筆 100 = 40 筆成功
    assert len(successes) == 40
    assert len(failures) == 60
    # ledger 與成功數一致
    assert ledger.total_reserved == Decimal("4000")
    assert ledger.symbol_available("BTCUSDT") == Decimal("0")


@pytest.mark.asyncio
async def test_fcfs_first_come_first_served_order() -> None:
    """前者先進 queue 即先處理：兩請求同時，前者必成功。"""
    ledger = ReservationLedger(
        total_equity=Decimal("100"),
        strategy_budgets={"A": Decimal("100")},
        symbol_caps={"BTCUSDT": Decimal("100")},
    )
    publisher = InMemoryEventPublisher()
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    reserver = CapitalReserver(ledger=ledger, clock=clock, publisher=publisher)

    await reserver.start()
    try:
        # Req-A 先 put，Req-B 後 put
        task_a = asyncio.create_task(
            reserver.reserve(intent=_intent(), notional=Decimal("70"))
        )
        # 給 task_a 機會先進 queue
        await asyncio.sleep(0.01)
        task_b = asyncio.create_task(
            reserver.reserve(intent=_intent(), notional=Decimal("70"))
        )

        result_a, result_b = await asyncio.gather(task_a, task_b)
    finally:
        await reserver.stop()

    assert result_a.ok is True
    assert result_b.ok is False
    assert result_b.reason == "strategy_budget_insufficient"


# ===== 啟停冪等 =====


@pytest.mark.asyncio
async def test_start_twice_raises() -> None:
    reserver, _, _ = _make_reserver()
    await reserver.start()
    try:
        with pytest.raises(RuntimeError, match="already started"):
            await reserver.start()
    finally:
        await reserver.stop()


@pytest.mark.asyncio
async def test_stop_idempotent() -> None:
    reserver, _, _ = _make_reserver()
    # 未啟動就 stop 不應拋
    await reserver.stop()
    await reserver.start()
    await reserver.stop()
    await reserver.stop()  # 第二次 stop


# ===== 策略區分 =====


@pytest.mark.asyncio
async def test_different_strategies_isolated_in_ledger() -> None:
    """兩策略分別預留不同標的，互不影響各自額度。"""
    reserver, ledger, _ = _make_reserver()
    # ledger 預設 strategy A=5000、B=4000、BTCUSDT=4000，其他 symbol 無限額
    await reserver.start()
    try:
        result_a = await reserver.reserve(
            intent=_intent(strategy_id="A", symbol="BTCUSDT"),
            notional=Decimal("3000"),
        )
        # 用不同 symbol（無限額）以排除 BTC 集中度耗盡導致互相影響
        result_b = await reserver.reserve(
            intent=_intent(strategy_id="B", symbol="ETHUSDT"),
            notional=Decimal("2000"),
        )
    finally:
        await reserver.stop()

    assert result_a.ok is True
    assert result_b.ok is True
    assert ledger.strategy_available("A") == Decimal("2000")
    assert ledger.strategy_available("B") == Decimal("2000")
