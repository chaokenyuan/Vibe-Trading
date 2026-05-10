"""SignalRouter 單元測試。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from signals.dedupe import SignalDedupe
from signals.registry_stub import InMemoryStrategyRegistry
from signals.router import SignalRouter
from signals.types import Signal, SignalSourceKind, StrategyMetadata
from tests.fakes.frozen_clock import FrozenClock


class _RecordingConsumer:
    """測試替身 SignalConsumer。"""

    def __init__(self) -> None:
        self.received: list[Signal] = []

    async def on_signal(self, signal: Signal) -> None:
        self.received.append(signal)


class _FailingConsumer:
    """總是丟例外的 consumer。"""

    async def on_signal(self, signal: Signal) -> None:
        raise RuntimeError("intentional failure")


class _StubSource:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


def _make_router(
    *, registered_strategies: list[str] | None = None,
) -> tuple[SignalRouter, InMemoryStrategyRegistry, FrozenClock, SignalDedupe]:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    registry = InMemoryStrategyRegistry()
    for sid in registered_strategies or ["A"]:
        registry.register(
            StrategyMetadata(
                strategy_id=sid,
                strategy_version="1.0.0",
                params_hash="hash",
            )
        )
    dedupe = SignalDedupe(clock=clock, ttl_seconds=300)
    router = SignalRouter(clock=clock, registry=registry, dedupe=dedupe)
    return router, registry, clock, dedupe


def _ingest_args(strategy_id: str = "A") -> dict[str, object]:
    return {
        "strategy_id": strategy_id,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": Decimal("1"),
        "price": Decimal("65000"),
        "bar_time": datetime(2026, 5, 10, tzinfo=UTC),
        "interval": "60",
        "source": SignalSourceKind.TRADINGVIEW,
        "comment": None,
        "raw_payload": {"v": 1},
    }


# ===== 補 metadata + signal_id =====


@pytest.mark.asyncio
async def test_ingest_known_strategy_succeeds() -> None:
    router, _, _, _ = _make_router()
    consumer = _RecordingConsumer()
    router.subscribe(consumer)

    signal = await router.ingest(**_ingest_args())  # type: ignore[arg-type]

    assert signal is not None
    assert len(consumer.received) == 1
    assert consumer.received[0].strategy_version == "1.0.0"
    assert consumer.received[0].params_hash == "hash"


@pytest.mark.asyncio
async def test_ingest_unknown_strategy_rejected() -> None:
    """spec scenario：未知 strategy_id 拒絕。"""
    router, _, _, _ = _make_router()
    consumer = _RecordingConsumer()
    router.subscribe(consumer)

    args = _ingest_args(strategy_id="UNKNOWN")
    signal = await router.ingest(**args)  # type: ignore[arg-type]

    assert signal is None
    assert consumer.received == []


@pytest.mark.asyncio
async def test_signal_id_deterministic() -> None:
    """spec scenario：signal_id 由固定欄位確定計算（同欄位同 ID）。"""
    router, _, clock, _ = _make_router()
    consumer = _RecordingConsumer()
    router.subscribe(consumer)

    s1 = await router.ingest(**_ingest_args())  # type: ignore[arg-type]
    # 推進時鐘但同 payload — signal_id 應仍相同（received_at 不影響）
    clock.advance(timedelta(seconds=400))  # 過 dedupe TTL
    s2 = await router.ingest(**_ingest_args())  # type: ignore[arg-type]

    assert s1 is not None and s2 is not None
    assert s1.signal_id == s2.signal_id


# ===== Dedupe =====


@pytest.mark.asyncio
async def test_duplicate_within_ttl_not_dispatched() -> None:
    """spec scenario：TTL 內重送被去重。"""
    router, _, clock, _ = _make_router()
    consumer = _RecordingConsumer()
    router.subscribe(consumer)

    await router.ingest(**_ingest_args())  # type: ignore[arg-type]
    clock.advance(timedelta(seconds=30))
    second = await router.ingest(**_ingest_args())  # type: ignore[arg-type]

    assert second is None
    assert len(consumer.received) == 1


@pytest.mark.asyncio
async def test_after_ttl_dispatched_again() -> None:
    """spec scenario：TTL 後同 signal_id 視為新訊號。"""
    router, _, clock, _ = _make_router()
    consumer = _RecordingConsumer()
    router.subscribe(consumer)

    await router.ingest(**_ingest_args())  # type: ignore[arg-type]
    clock.advance(timedelta(seconds=301))
    second = await router.ingest(**_ingest_args())  # type: ignore[arg-type]

    assert second is not None
    assert len(consumer.received) == 2


# ===== Fan-out =====


@pytest.mark.asyncio
async def test_multiple_consumers_all_receive() -> None:
    """spec scenario：多 consumer fan-out。"""
    router, _, _, _ = _make_router()
    a = _RecordingConsumer()
    b = _RecordingConsumer()
    router.subscribe(a)
    router.subscribe(b)

    await router.ingest(**_ingest_args())  # type: ignore[arg-type]

    assert len(a.received) == 1
    assert len(b.received) == 1


@pytest.mark.asyncio
async def test_failing_consumer_does_not_break_others() -> None:
    """spec scenario：一 consumer 失敗其他繼續。"""
    router, _, _, _ = _make_router()
    failing = _FailingConsumer()
    succeeding = _RecordingConsumer()
    router.subscribe(failing)
    router.subscribe(succeeding)

    signal = await router.ingest(**_ingest_args())  # type: ignore[arg-type]

    assert signal is not None
    assert len(succeeding.received) == 1


# ===== Lifecycle =====


@pytest.mark.asyncio
async def test_start_starts_all_sources() -> None:
    """spec scenario：start 成功啟動所有 source。"""
    router, _, _, _ = _make_router()
    s1 = _StubSource()
    s2 = _StubSource()
    router.attach_source(s1)
    router.attach_source(s2)

    await router.start()
    try:
        assert s1.started is True
        assert s2.started is True
    finally:
        await router.stop()
        assert s1.stopped is True
        assert s2.stopped is True


@pytest.mark.asyncio
async def test_double_start_raises() -> None:
    router, _, _, _ = _make_router()
    await router.start()
    try:
        with pytest.raises(RuntimeError, match="already started"):
            await router.start()
    finally:
        await router.stop()


@pytest.mark.asyncio
async def test_stop_idempotent() -> None:
    router, _, _, _ = _make_router()
    await router.stop()  # 未啟動就 stop
    await router.start()
    await router.stop()
    await router.stop()  # 第二次 stop


# ===== received_at =====


@pytest.mark.asyncio
async def test_received_at_uses_clock() -> None:
    router, _, clock, _ = _make_router()
    consumer = _RecordingConsumer()
    router.subscribe(consumer)

    fixed_time = datetime(2026, 5, 10, 12, 34, 56, tzinfo=UTC)
    clock.set(fixed_time)
    await router.ingest(**_ingest_args())  # type: ignore[arg-type]

    assert consumer.received[0].received_at == fixed_time
