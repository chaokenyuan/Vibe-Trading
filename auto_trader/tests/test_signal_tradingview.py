"""TradingViewWebhookAdapter + create_tradingview_app 測試。

使用 httpx.ASGITransport 直接打 FastAPI app，避免啟動 uvicorn。
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest

from signals.adapters.tradingview import (
    TradingViewWebhookAdapter,
    create_tradingview_app,
)
from signals.config import TradingViewConfig
from signals.dedupe import SignalDedupe
from signals.registry_stub import InMemoryStrategyRegistry
from signals.router import SignalRouter
from signals.types import Signal, StrategyMetadata
from tests.fakes.frozen_clock import FrozenClock


class _RecordingConsumer:
    def __init__(self) -> None:
        self.received: list[Signal] = []

    async def on_signal(self, signal: Signal) -> None:
        self.received.append(signal)


def _make_app_and_consumer(
    *,
    secret: str = "test_secret_8",
    allowed_ips: list[str] | None = None,
) -> tuple[Any, _RecordingConsumer, FrozenClock]:
    if allowed_ips is None:
        allowed_ips = []  # 空清單 = 接受全部（測試模式）

    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    registry = InMemoryStrategyRegistry()
    registry.register(
        StrategyMetadata(strategy_id="A", strategy_version="1.0.0", params_hash="hash")
    )
    dedupe = SignalDedupe(clock=clock, ttl_seconds=300)
    router = SignalRouter(clock=clock, registry=registry, dedupe=dedupe)
    consumer = _RecordingConsumer()
    router.subscribe(consumer)

    config = TradingViewConfig(secret=secret, allowed_ips=allowed_ips)
    adapter = TradingViewWebhookAdapter()
    app = create_tradingview_app(adapter=adapter, router=router, config=config)
    return app, consumer, clock


def _valid_payload() -> dict[str, Any]:
    return {
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


# ===== 認證 =====


@pytest.mark.asyncio
async def test_correct_secret_and_allowed_ip_accepted() -> None:
    """spec scenario：secret 正確 + IP 白名單 → 200。"""
    app, consumer, _ = _make_app_and_consumer(secret="test_secret_8")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/webhook/tv/test_secret_8/A", json=_valid_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "accepted"
    assert "signal_id" in body
    assert len(consumer.received) == 1


@pytest.mark.asyncio
async def test_wrong_secret_returns_401() -> None:
    """spec scenario：secret 錯誤 → 401。"""
    app, _, _ = _make_app_and_consumer(secret="correct_secret_8")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/webhook/tv/wrong_secret/A", json=_valid_payload())
    assert resp.status_code == 401
    assert resp.json()["detail"] == "unauthorized"


@pytest.mark.asyncio
async def test_ip_not_in_whitelist_returns_401() -> None:
    """spec scenario：IP 不白名單 → 401。"""
    app, _, _ = _make_app_and_consumer(
        secret="test_secret_8", allowed_ips=["1.2.3.4"]
    )
    transport = httpx.ASGITransport(app=app, client=("9.9.9.9", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/webhook/tv/test_secret_8/A", json=_valid_payload())
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_empty_allowed_ips_accepts_all() -> None:
    """spec scenario：空 allowed_ips（測試模式）接受全部。"""
    app, consumer, _ = _make_app_and_consumer(
        secret="test_secret_8", allowed_ips=[]
    )
    transport = httpx.ASGITransport(app=app, client=("1.2.3.4", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/webhook/tv/test_secret_8/A", json=_valid_payload())
    assert resp.status_code == 200
    assert len(consumer.received) == 1


# ===== JSON / Schema =====


@pytest.mark.asyncio
async def test_invalid_json_returns_422() -> None:
    """spec scenario：無效 JSON → 422。"""
    app, _, _ = _make_app_and_consumer(secret="test_secret_8")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/webhook/tv/test_secret_8/A",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_missing_field_returns_422() -> None:
    """spec scenario：缺欄位 → 422。"""
    app, _, _ = _make_app_and_consumer(secret="test_secret_8")
    payload = _valid_payload()
    del payload["strategy_id"]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # url 也要對應移除（否則會更早被 mismatch 攔截）
        resp = await ac.post("/webhook/tv/test_secret_8/A", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unsupported_schema_version_returns_422() -> None:
    """spec scenario：schema_version 不為 1 → 422。"""
    app, _, _ = _make_app_and_consumer(secret="test_secret_8")
    payload = _valid_payload()
    payload["v"] = 2
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/webhook/tv/test_secret_8/A", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_strategy_id_mismatch_url_vs_payload_returns_422() -> None:
    app, _, _ = _make_app_and_consumer(secret="test_secret_8")
    payload = _valid_payload()
    payload["strategy_id"] = "B"  # url 是 A
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/webhook/tv/test_secret_8/A", json=payload)
    assert resp.status_code == 422


# ===== parse_payload 單元 =====


def test_parse_payload_valid() -> None:
    parsed = TradingViewWebhookAdapter.parse_payload(_valid_payload())
    assert parsed["strategy_id"] == "A"
    assert parsed["qty"] == Decimal("1")
    assert parsed["price"] == Decimal("65000")
    assert parsed["side"] == "BUY"


def test_parse_payload_invalid_side_raises() -> None:
    payload = _valid_payload()
    payload["side"] = "HOLD"
    with pytest.raises(ValueError, match="invalid side"):
        TradingViewWebhookAdapter.parse_payload(payload)


def test_parse_payload_invalid_qty_raises() -> None:
    payload = _valid_payload()
    payload["qty"] = "abc"
    with pytest.raises(ValueError, match="invalid qty"):
        TradingViewWebhookAdapter.parse_payload(payload)


def test_parse_payload_null_price_ok() -> None:
    payload = _valid_payload()
    payload["price"] = None
    parsed = TradingViewWebhookAdapter.parse_payload(payload)
    assert parsed["price"] is None


def test_parse_payload_invalid_bar_time_raises() -> None:
    payload = _valid_payload()
    payload["bar_time"] = "not-a-date"
    with pytest.raises(ValueError, match="invalid bar_time"):
        TradingViewWebhookAdapter.parse_payload(payload)


# ===== Adapter lifecycle =====


@pytest.mark.asyncio
async def test_adapter_start_stop_noop() -> None:
    adapter = TradingViewWebhookAdapter()
    await adapter.start()
    await adapter.stop()  # 不應拋
