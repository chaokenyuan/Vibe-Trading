"""reconciliation capability 測試。"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from reconciliation.adapters.ccxt_stub import CcxtFillSource
from reconciliation.adapters.mock import MockFillSource
from reconciliation.broker_book import BrokerPositionTracker
from reconciliation.events import FillProcessed
from reconciliation.ports import FillSource
from reconciliation.position_reader import BookPositionReader
from reconciliation.processor import FillProcessor
from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.events import Event
from risk.ports import PositionReader
from risk.types import Side
from strategies.registry import StrategyRegistry
from strategies.strategies.passthrough import PassthroughStrategy
from strategies.types import Fill, StrategyState
from tests.fakes.frozen_clock import FrozenClock


def _strategy(strategy_id: str = "A") -> PassthroughStrategy:
    return PassthroughStrategy(
        strategy_id=strategy_id, strategy_version="1.0.0", params_hash="hash"
    )


def _fill(
    *,
    strategy_id: str = "A",
    side: Side = Side.BUY,
    qty: Decimal = Decimal("1"),
    price: Decimal = Decimal("65000"),
    symbol: str = "BTCUSDT",
) -> Fill:
    return Fill(
        fill_id=uuid4(),
        client_order_id=f"{strategy_id}.abc123def456.1",
        broker_order_id="bo-1",
        symbol=symbol,
        side=side,
        qty=qty,
        price=price,
        fees=Decimal("0"),
        at=datetime(2026, 5, 10, tzinfo=UTC),
    )


def _make_processor() -> tuple[FillProcessor, StrategyRegistry, list[Event]]:
    registry = StrategyRegistry()
    registry.register(_strategy("A"))
    registry.set_state("A", StrategyState.ACTIVE)
    publisher = InMemoryEventPublisher()
    received: list[Event] = []

    async def cap(e: Event) -> None:
        received.append(e)

    publisher.subscribe(Event, cap)

    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    processor = FillProcessor(registry=registry, publisher=publisher, clock=clock)
    return processor, registry, received


# ===== FillProcessor =====


@pytest.mark.asyncio
async def test_fill_updates_logical_book() -> None:
    """spec scenario：已知策略的 Fill 更新 LogicalBook。"""
    processor, registry, received = _make_processor()
    fill = _fill()
    await processor.on_fill(fill)

    book = registry.get_book("A")
    assert book is not None
    pos = book.get_position("BTCUSDT")
    assert pos is not None
    assert pos.qty == Decimal("1")

    processed = [e for e in received if isinstance(e, FillProcessed)]
    assert len(processed) == 1
    assert processed[0].strategy_id == "A"


@pytest.mark.asyncio
async def test_fill_unknown_strategy_skipped() -> None:
    """spec scenario：未知策略的 Fill 跳過。"""
    processor, registry, received = _make_processor()
    fill = _fill(strategy_id="UNKNOWN")
    await processor.on_fill(fill)

    # 沒任何 strategy 的 book 受影響
    assert registry.get_book("A") is not None
    assert registry.get_book("A").get_position("BTCUSDT") is None  # type: ignore[union-attr]

    processed = [e for e in received if isinstance(e, FillProcessed)]
    assert processed == []


@pytest.mark.asyncio
async def test_duplicate_fill_id_skipped() -> None:
    """spec scenario：重複 fill_id 去重。"""
    processor, registry, received = _make_processor()
    fill = _fill()
    await processor.on_fill(fill)
    await processor.on_fill(fill)

    book = registry.get_book("A")
    assert book is not None
    pos = book.get_position("BTCUSDT")
    assert pos is not None
    # 只應有一筆持倉（qty=1，不是 2）
    assert pos.qty == Decimal("1")

    processed = [e for e in received if isinstance(e, FillProcessed)]
    assert len(processed) == 1


# ===== BrokerPositionTracker =====


@pytest.mark.asyncio
async def test_broker_tracker_sums_strategies() -> None:
    """spec scenario：多策略同 symbol 持倉相加。"""
    registry = StrategyRegistry()
    registry.register(_strategy("A"))
    registry.register(_strategy("B"))
    publisher = InMemoryEventPublisher()
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    processor = FillProcessor(registry=registry, publisher=publisher, clock=clock)

    # A long 1 BTC
    await processor.on_fill(_fill(strategy_id="A", side=Side.BUY, qty=Decimal("1")))
    # B short 0.5 BTC
    await processor.on_fill(
        _fill(strategy_id="B", side=Side.SELL, qty=Decimal("0.5"))
    )

    tracker = BrokerPositionTracker(registry=registry)
    assert tracker.get_total_position("BTCUSDT") == Decimal("0.5")


def test_broker_tracker_no_position_returns_zero() -> None:
    """spec scenario：無持倉回 0。"""
    registry = StrategyRegistry()
    registry.register(_strategy("A"))
    tracker = BrokerPositionTracker(registry=registry)
    assert tracker.get_total_position("ETHUSDT") == Decimal("0")


@pytest.mark.asyncio
async def test_broker_tracker_lists_symbols_with_position() -> None:
    registry = StrategyRegistry()
    registry.register(_strategy("A"))
    publisher = InMemoryEventPublisher()
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    processor = FillProcessor(registry=registry, publisher=publisher, clock=clock)

    await processor.on_fill(_fill(strategy_id="A", symbol="BTCUSDT"))
    await processor.on_fill(_fill(strategy_id="A", symbol="ETHUSDT", price=Decimal("3000")))

    tracker = BrokerPositionTracker(registry=registry)
    assert sorted(tracker.list_symbols_with_position()) == ["BTCUSDT", "ETHUSDT"]


# ===== BookPositionReader =====


def test_book_position_reader_satisfies_protocol() -> None:
    """spec scenario：結構性符合 PositionReader。"""
    registry = StrategyRegistry()
    reader = BookPositionReader(registry=registry)
    assert isinstance(reader, PositionReader)


@pytest.mark.asyncio
async def test_book_reader_returns_positions() -> None:
    """spec scenario：get_position 回對應 LogicalPosition；list_positions 列出全部。"""
    registry = StrategyRegistry()
    registry.register(_strategy("A"))
    publisher = InMemoryEventPublisher()
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    processor = FillProcessor(registry=registry, publisher=publisher, clock=clock)
    await processor.on_fill(_fill(strategy_id="A"))

    reader = BookPositionReader(registry=registry)
    pos = reader.get_position("A", "BTCUSDT")
    assert pos is not None
    assert pos.qty == Decimal("1")

    positions = reader.list_positions()
    assert len(positions) == 1


def test_book_reader_unknown_strategy_returns_none() -> None:
    registry = StrategyRegistry()
    reader = BookPositionReader(registry=registry)
    assert reader.get_position("X", "BTCUSDT") is None
    assert reader.list_positions() == []


# ===== FillSource Protocol + Mock + stub =====


@pytest.mark.asyncio
async def test_mock_fill_source_push_triggers_callback() -> None:
    """spec scenario：MockFillSource 手動推送觸發 callback。"""
    received: list[Fill] = []

    async def cb(fill: Fill) -> None:
        received.append(fill)

    source = MockFillSource(callback=cb)
    await source.start()
    fill = _fill()
    await source.push(fill)
    await source.stop()
    assert received == [fill]


@pytest.mark.asyncio
async def test_mock_fill_source_push_before_start_raises() -> None:
    async def cb(fill: Fill) -> None:
        pass

    source = MockFillSource(callback=cb)
    with pytest.raises(RuntimeError):
        await source.push(_fill())


@pytest.mark.asyncio
async def test_ccxt_fill_source_stub_raises() -> None:
    """spec scenario：CcxtFillSource stub 拋 NotImplementedError。"""
    async def cb(fill: Fill) -> None:
        pass

    source = CcxtFillSource(callback=cb)
    with pytest.raises(NotImplementedError):
        await source.start()
    with pytest.raises(NotImplementedError):
        await source.stop()


def test_mock_fill_source_satisfies_protocol() -> None:
    async def cb(fill: Fill) -> None:
        pass

    assert isinstance(MockFillSource(callback=cb), FillSource)


def test_ccxt_fill_source_satisfies_protocol() -> None:
    async def cb(fill: Fill) -> None:
        pass

    assert isinstance(CcxtFillSource(callback=cb), FillSource)


# ===== e2e =====


@pytest.mark.asyncio
async def test_e2e_mock_fill_source_to_logical_book() -> None:
    registry = StrategyRegistry()
    registry.register(_strategy("A"))
    publisher = InMemoryEventPublisher()
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    processor = FillProcessor(registry=registry, publisher=publisher, clock=clock)

    source = MockFillSource(callback=processor.on_fill)
    await source.start()
    try:
        await source.push(_fill(strategy_id="A", side=Side.BUY, qty=Decimal("2")))
        await source.push(
            _fill(strategy_id="A", side=Side.BUY, qty=Decimal("1"), price=Decimal("66000"))
        )
    finally:
        await source.stop()

    book = registry.get_book("A")
    assert book is not None
    pos = book.get_position("BTCUSDT")
    assert pos is not None
    # 加權平均 = (2*65000 + 1*66000) / 3 = 65333.33...
    assert pos.qty == Decimal("3")
