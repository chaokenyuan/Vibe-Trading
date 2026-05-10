"""signal-ingestion 端到端整合測試。

涵蓋：
- TV webhook 完整流程（FastAPI app → router → consumer）
- 100 並發 webhook 請求 → dedupe + fan-out 一致
- 未知 strategy_id 經 webhook 接收後被 router 拒（200 應答但不分發）
- ManualCliAdapter + TradingViewWebhookAdapter 並用、跨 source dedupe
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest

from signals.adapters.manual_cli import ManualCliAdapter
from signals.adapters.tradingview import (
    TradingViewWebhookAdapter,
    create_tradingview_app,
)
from signals.config import TradingViewConfig
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


@pytest.mark.asyncio
async def test_webhook_e2e_dispatches_to_consumer() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    registry = InMemoryStrategyRegistry()
    registry.register(
        StrategyMetadata(strategy_id="A", strategy_version="1.0.0", params_hash="h")
    )
    dedupe = SignalDedupe(clock=clock, ttl_seconds=300)
    router = SignalRouter(clock=clock, registry=registry, dedupe=dedupe)
    consumer = _RecordingConsumer()
    router.subscribe(consumer)

    adapter = TradingViewWebhookAdapter()
    config = TradingViewConfig(secret="test_secret_8", allowed_ips=[])
    app = create_tradingview_app(adapter=adapter, router=router, config=config)

    payload: dict[str, Any] = {
        "v": 1,
        "strategy_id": "A",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": "1",
        "price": "65000",
        "bar_time": "2026-05-10T12:00:00+00:00",
        "interval": "60",
        "comment": None,
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/webhook/tv/test_secret_8/A", json=payload)

    assert resp.status_code == 200
    assert len(consumer.received) == 1
    received_signal = consumer.received[0]
    assert received_signal.source == SignalSourceKind.TRADINGVIEW
    assert received_signal.strategy_version == "1.0.0"
    assert received_signal.qty == Decimal("1")


@pytest.mark.asyncio
async def test_webhook_unknown_strategy_id_returns_200_but_no_dispatch() -> None:
    """未知 strategy_id：webhook 接受了 200 但 router 內部拒，consumer 不收。"""
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    registry = InMemoryStrategyRegistry()  # 空
    dedupe = SignalDedupe(clock=clock, ttl_seconds=300)
    router = SignalRouter(clock=clock, registry=registry, dedupe=dedupe)
    consumer = _RecordingConsumer()
    router.subscribe(consumer)

    adapter = TradingViewWebhookAdapter()
    config = TradingViewConfig(secret="test_secret_8", allowed_ips=[])
    app = create_tradingview_app(adapter=adapter, router=router, config=config)

    payload: dict[str, Any] = {
        "v": 1,
        "strategy_id": "UNKNOWN",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": "1",
        "price": "65000",
        "bar_time": "2026-05-10T12:00:00+00:00",
        "interval": "60",
        "comment": None,
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/webhook/tv/test_secret_8/UNKNOWN", json=payload)

    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert consumer.received == []


@pytest.mark.asyncio
async def test_concurrent_webhook_requests_dedupe_unique_signal() -> None:
    """100 並發 webhook 請求（同 payload）→ 只有第一筆通過，其他被 dedupe。"""
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    registry = InMemoryStrategyRegistry()
    registry.register(
        StrategyMetadata(strategy_id="A", strategy_version="1.0.0", params_hash="h")
    )
    dedupe = SignalDedupe(clock=clock, ttl_seconds=300)
    router = SignalRouter(clock=clock, registry=registry, dedupe=dedupe)
    consumer = _RecordingConsumer()
    router.subscribe(consumer)

    adapter = TradingViewWebhookAdapter()
    config = TradingViewConfig(secret="test_secret_8", allowed_ips=[])
    app = create_tradingview_app(adapter=adapter, router=router, config=config)

    payload: dict[str, Any] = {
        "v": 1,
        "strategy_id": "A",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": "1",
        "price": "65000",
        "bar_time": "2026-05-10T12:00:00+00:00",
        "interval": "60",
        "comment": None,
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        tasks = [
            ac.post("/webhook/tv/test_secret_8/A", json=payload) for _ in range(100)
        ]
        responses = await asyncio.gather(*tasks)

    accepted = [r for r in responses if r.json()["status"] == "accepted"]
    rejected = [r for r in responses if r.json()["status"] == "rejected"]
    assert len(accepted) == 1
    assert len(rejected) == 99
    assert len(consumer.received) == 1


@pytest.mark.asyncio
async def test_cross_source_dedupe_manual_then_webhook() -> None:
    """同一 signal_id 透過 ManualCliAdapter 與 webhook 各送一次：第二次被 dedupe。"""
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    registry = InMemoryStrategyRegistry()
    registry.register(
        StrategyMetadata(strategy_id="A", strategy_version="1.0.0", params_hash="h")
    )
    dedupe = SignalDedupe(clock=clock, ttl_seconds=300)
    router = SignalRouter(clock=clock, registry=registry, dedupe=dedupe)
    consumer = _RecordingConsumer()
    router.subscribe(consumer)

    # 1. Manual 先送
    manual_adapter = ManualCliAdapter(router=router)
    bar_time = datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)
    manual_signal = Signal(
        schema_version=SCHEMA_VERSION_CURRENT,
        signal_id="placeholder",
        strategy_id="A",
        strategy_version="1.0.0",
        params_hash="h",
        symbol="BTCUSDT",
        side="BUY",
        qty=Decimal("1"),
        price=None,
        bar_time=bar_time,
        interval="60",
        received_at=clock.now(),
        source=SignalSourceKind.MANUAL,
        comment=None,
        raw_payload={"manual": True},
    )
    await manual_adapter.submit(manual_signal)
    assert len(consumer.received) == 1

    # 2. Webhook 用相同 strategy_id/symbol/side/bar_time/interval → 同 signal_id
    adapter = TradingViewWebhookAdapter()
    config = TradingViewConfig(secret="test_secret_8", allowed_ips=[])
    app = create_tradingview_app(adapter=adapter, router=router, config=config)

    payload: dict[str, Any] = {
        "v": 1,
        "strategy_id": "A",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": "1",
        "price": "65000",
        "bar_time": bar_time.isoformat(),
        "interval": "60",
        "comment": None,
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/webhook/tv/test_secret_8/A", json=payload)

    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"  # router 內部 dedupe 命中
    # consumer 仍只收一筆
    assert len(consumer.received) == 1
