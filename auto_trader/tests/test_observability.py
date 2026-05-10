"""observability capability 完整測試。"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from execution.events import OrderRejectedByBroker
from observability.adapters.logging_sink import LoggingAlertSink
from observability.adapters.telegram_stub import TelegramAlertSink
from observability.alert_router import AlertRouter
from observability.audit_log import AuditLogWriter
from observability.config import ObservabilityConfig
from observability.health import create_health_app
from observability.ports import AlertSink
from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.decision import Decision, Verdict
from risk.events import (
    ConfigLoaded,
    DailyPnlReset,
    DecisionEmitted,
    EmergencyFlattenRequested,
    StateChanged,
)
from tests.fakes.frozen_clock import FrozenClock

# ===== AlertSink Protocol + 實作 =====


def test_logging_sink_satisfies_protocol() -> None:
    assert isinstance(LoggingAlertSink(), AlertSink)


def test_telegram_stub_satisfies_protocol() -> None:
    assert isinstance(TelegramAlertSink(), AlertSink)


@pytest.mark.asyncio
async def test_logging_sink_calls_logger(caplog: pytest.LogCaptureFixture) -> None:
    """spec scenario：LoggingAlertSink 呼叫 stdlib logger。"""
    sink = LoggingAlertSink()
    with caplog.at_level(logging.ERROR, logger="vibe.alerts"):
        await sink.send(level="error", message="boom", context={"k": "v"})
    assert any("boom" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_telegram_stub_raises_not_implemented() -> None:
    """spec scenario：TelegramAlertSink stub 拋 NotImplementedError。"""
    sink = TelegramAlertSink()
    with pytest.raises(NotImplementedError):
        await sink.send(level="info", message="x", context={})


# ===== AuditLogWriter =====


@pytest.mark.asyncio
async def test_audit_log_writes_one_line_per_event(tmp_path: Path) -> None:
    """spec scenario：寫入單行 JSON。"""
    publisher = InMemoryEventPublisher()
    log_path = tmp_path / "audit.jsonl"
    writer = AuditLogWriter(publisher=publisher, log_path=log_path)
    writer.start()

    await publisher.publish(ConfigLoaded(at=datetime(2026, 5, 10, tzinfo=UTC), params_hash="h"))

    content = log_path.read_text(encoding="utf-8")
    lines = [line for line in content.split("\n") if line]
    assert len(lines) == 1
    decoded = json.loads(lines[0])
    assert decoded["params_hash"] == "h"


@pytest.mark.asyncio
async def test_audit_log_multiple_events_multiple_lines(tmp_path: Path) -> None:
    """spec scenario：多事件多行。"""
    publisher = InMemoryEventPublisher()
    log_path = tmp_path / "audit.jsonl"
    writer = AuditLogWriter(publisher=publisher, log_path=log_path)
    writer.start()

    for i in range(3):
        await publisher.publish(
            ConfigLoaded(at=datetime(2026, 5, 10, tzinfo=UTC), params_hash=f"h{i}")
        )

    lines = [
        line
        for line in log_path.read_text(encoding="utf-8").split("\n")
        if line
    ]
    assert len(lines) == 3
    for line in lines:
        json.loads(line)  # 每行皆有效 JSON


@pytest.mark.asyncio
async def test_audit_log_creates_parent_dir(tmp_path: Path) -> None:
    publisher = InMemoryEventPublisher()
    log_path = tmp_path / "deeply" / "nested" / "audit.jsonl"
    writer = AuditLogWriter(publisher=publisher, log_path=log_path)
    writer.start()
    await publisher.publish(
        ConfigLoaded(at=datetime(2026, 5, 10, tzinfo=UTC), params_hash="h")
    )
    assert log_path.exists()


# ===== AlertRouter =====


class _RecordingSink:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def send(
        self, *, level: str, message: str, context: dict[str, Any]
    ) -> None:
        self.calls.append((level, message, context))


@pytest.mark.asyncio
async def test_kill_switch_event_triggers_critical_alert() -> None:
    """spec scenario：KILL_SWITCH 事件觸發 critical 告警。"""
    publisher = InMemoryEventPublisher()
    sink = _RecordingSink()
    router = AlertRouter(publisher=publisher, sink=sink)
    router.start()

    await publisher.publish(EmergencyFlattenRequested(at=datetime(2026, 5, 10, tzinfo=UTC)))
    assert len(sink.calls) == 1
    level, msg, _ctx = sink.calls[0]
    assert level == "critical"
    assert "KILL_SWITCH" in msg


@pytest.mark.asyncio
async def test_state_changed_to_halted_warning() -> None:
    publisher = InMemoryEventPublisher()
    sink = _RecordingSink()
    router = AlertRouter(publisher=publisher, sink=sink)
    router.start()

    await publisher.publish(
        StateChanged(
            at=datetime(2026, 5, 10, tzinfo=UTC),
            from_state="NORMAL",
            to_state="HALTED",
            reason="test",
        )
    )
    assert sink.calls[0][0] == "warning"


@pytest.mark.asyncio
async def test_order_rejected_by_broker_alert() -> None:
    publisher = InMemoryEventPublisher()
    sink = _RecordingSink()
    router = AlertRouter(publisher=publisher, sink=sink)
    router.start()

    await publisher.publish(
        OrderRejectedByBroker(
            at=datetime(2026, 5, 10, tzinfo=UTC),
            client_order_id="A.x.1",
            symbol="BTCUSDT",
            strategy_id="A",
            reason="balance",
        )
    )
    assert sink.calls[0][0] == "error"
    assert "A.x.1" in sink.calls[0][1]


@pytest.mark.asyncio
async def test_decision_emitted_does_not_alert() -> None:
    """spec scenario：不在白名單事件不告警。"""
    publisher = InMemoryEventPublisher()
    sink = _RecordingSink()
    router = AlertRouter(publisher=publisher, sink=sink)
    router.start()

    decision = Decision(
        verdict=Verdict.APPROVE,
        final_size=Decimal("1"),
        final_price=None,
        reasons=[],
        reservation_id=None,
        evaluated_at=datetime(2026, 5, 10, tzinfo=UTC),
    )
    await publisher.publish(
        DecisionEmitted(at=datetime(2026, 5, 10, tzinfo=UTC), decision=decision)
    )
    assert sink.calls == []


@pytest.mark.asyncio
async def test_config_loaded_info_alert() -> None:
    publisher = InMemoryEventPublisher()
    sink = _RecordingSink()
    router = AlertRouter(publisher=publisher, sink=sink)
    router.start()

    await publisher.publish(
        ConfigLoaded(at=datetime(2026, 5, 10, tzinfo=UTC), params_hash="abc" * 30)
    )
    assert sink.calls[0][0] == "info"


@pytest.mark.asyncio
async def test_daily_pnl_reset_info_alert() -> None:
    publisher = InMemoryEventPublisher()
    sink = _RecordingSink()
    router = AlertRouter(publisher=publisher, sink=sink)
    router.start()

    await publisher.publish(DailyPnlReset(at=datetime(2026, 5, 10, tzinfo=UTC)))
    assert sink.calls[0][0] == "info"


# ===== Health endpoint =====


@pytest.mark.asyncio
async def test_health_endpoint_returns_200() -> None:
    """spec scenario：/health 回 200。"""
    clock = FrozenClock(initial=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC))
    app = create_health_app(clock=clock)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "vibe-auto-trader"


@pytest.mark.asyncio
async def test_readyz_returns_200_when_ready() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    app = create_health_app(clock=clock, is_ready=lambda: True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/readyz")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_readyz_returns_503_when_not_ready() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    app = create_health_app(clock=clock, is_ready=lambda: False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/readyz")
    assert resp.status_code == 503


# ===== Config =====


def test_observability_config_default() -> None:
    cfg = ObservabilityConfig()
    assert cfg.audit_log.enabled is True
    assert cfg.telegram.enabled is False
    assert cfg.health.service_name == "vibe-auto-trader"


def test_observability_config_from_yaml(tmp_path: Path) -> None:
    p = tmp_path / "obs.yaml"
    p.write_text("audit_log:\n  enabled: false\n", encoding="utf-8")
    cfg = ObservabilityConfig.from_yaml(p)
    assert cfg.audit_log.enabled is False
