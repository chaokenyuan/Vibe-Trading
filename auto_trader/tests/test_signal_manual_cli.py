"""ManualCliAdapter 測試。"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from signals.adapters.manual_cli import ManualCliAdapter
from signals.dedupe import SignalDedupe
from signals.registry_stub import InMemoryStrategyRegistry
from signals.router import SignalRouter
from signals.types import (
    SCHEMA_VERSION_CURRENT,
    Signal,
    SignalSourceKind,
    StrategyMetadata,
)
from tests.fakes.frozen_clock import FrozenClock


class _RecordingConsumer:
    def __init__(self) -> None:
        self.received: list[Signal] = []

    async def on_signal(self, signal: Signal) -> None:
        self.received.append(signal)


def _make() -> tuple[ManualCliAdapter, SignalRouter, _RecordingConsumer]:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    registry = InMemoryStrategyRegistry()
    registry.register(
        StrategyMetadata(strategy_id="A", strategy_version="1.0.0", params_hash="hash")
    )
    dedupe = SignalDedupe(clock=clock, ttl_seconds=300)
    router = SignalRouter(clock=clock, registry=registry, dedupe=dedupe)
    consumer = _RecordingConsumer()
    router.subscribe(consumer)
    adapter = ManualCliAdapter(router=router)
    return adapter, router, consumer


def _signal_with_source(source: SignalSourceKind) -> Signal:
    return Signal(
        schema_version=SCHEMA_VERSION_CURRENT,
        signal_id="placeholder",  # router 會重新計算
        strategy_id="A",
        strategy_version="1.0.0",
        params_hash="hash",
        symbol="BTCUSDT",
        side="BUY",
        qty=Decimal("1"),
        price=None,
        bar_time=datetime(2026, 5, 10, tzinfo=UTC),
        interval="60",
        received_at=datetime(2026, 5, 10, 0, 0, 1, tzinfo=UTC),
        source=source,
        comment=None,
        raw_payload={"manual": True},
    )


@pytest.mark.asyncio
async def test_submit_with_manual_source_succeeds() -> None:
    adapter, _, consumer = _make()
    await adapter.submit(_signal_with_source(SignalSourceKind.MANUAL))
    assert len(consumer.received) == 1
    assert consumer.received[0].source == SignalSourceKind.MANUAL


@pytest.mark.asyncio
async def test_submit_with_non_manual_source_raises() -> None:
    """spec scenario：source 不為 manual 拒絕。"""
    adapter, _, _ = _make()
    with pytest.raises(ValueError, match="manual"):
        await adapter.submit(_signal_with_source(SignalSourceKind.TRADINGVIEW))


@pytest.mark.asyncio
async def test_adapter_start_stop_noop() -> None:
    adapter, _, _ = _make()
    await adapter.start()
    await adapter.stop()
