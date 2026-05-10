"""RiskGate 門面測試。

對應 spec scenario：
- 暖機期內拒絕 OrderIntent
- 暖機期結束後正常處理
- shutdown 後不接受新請求
- from_config 端到端建構
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.config import RiskConfig
from risk.decision import Verdict
from risk.events import ConfigLoaded, Event
from risk.gate import RiskGate
from risk.reservation.ledger import ReservationLedger
from risk.state.persistence import InMemoryStateStore
from risk.types import OrderIntent, Side
from tests.fakes.frozen_clock import FrozenClock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "risk.yaml"


class _FakePositions:
    def get_position(self, strategy_id: str, symbol: str) -> Any:
        return None

    def list_positions(self) -> list[Any]:
        return []


class _FakeMarket:
    def get_last_price(self, symbol: str) -> Decimal:
        return Decimal("65000")


class _FakeConfig:
    def get(self, key: str) -> Any:
        return None


def _make_gate(
    *,
    enabled_rules: list[str] | None = None,
    initial_state: str | None = None,
) -> tuple[RiskGate, FrozenClock, InMemoryEventPublisher, list[Event]]:
    config = RiskConfig.from_yaml(DEFAULT_CONFIG)
    if enabled_rules is not None:
        config = config.model_copy(
            update={"rules": config.rules.model_copy(update={"enabled": enabled_rules})}
        )

    clock = FrozenClock(initial=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC))
    store = InMemoryStateStore()
    if initial_state is not None:
        store.save_state(initial_state)
    publisher = InMemoryEventPublisher()
    received: list[Event] = []

    async def capture(e: Event) -> None:
        received.append(e)

    publisher.subscribe(Event, capture)

    ledger = ReservationLedger(
        total_equity=Decimal("10000"),
        strategy_budgets={"A": Decimal("5000")},
        symbol_caps={"BTCUSDT": Decimal("4000")},
    )

    gate = RiskGate(
        config=config,
        clock=clock,
        store=store,
        publisher=publisher,
        positions=_FakePositions(),
        market_data=_FakeMarket(),
        config_reader=_FakeConfig(),
        ledger=ledger,
    )
    return gate, clock, publisher, received


def _intent() -> OrderIntent:
    return OrderIntent(
        strategy_id="A",
        symbol="BTCUSDT",
        side=Side.BUY,
        qty=Decimal("1"),
        price=Decimal("65000"),
        signal_id="sig",
        bar_time=datetime(2026, 5, 10, tzinfo=UTC),
        received_at=datetime(2026, 5, 10, 0, 0, 1, tzinfo=UTC),
    )


# ===== 暖機期 =====


@pytest.mark.asyncio
async def test_warming_up_rejects_order_intent() -> None:
    """spec scenario：暖機期間拒絕 OrderIntent。"""
    gate, _, _, _ = _make_gate(enabled_rules=["SystemStateRule", "IdempotencyRule"])
    await gate.start()
    try:
        decision = await gate.evaluate(_intent())
    finally:
        await gate.shutdown()

    assert decision.verdict == Verdict.REJECT
    assert any(r.message == "system_warming_up" for r in decision.reasons)


@pytest.mark.asyncio
async def test_warming_up_metadata_includes_remaining_seconds() -> None:
    gate, _clock, _, _ = _make_gate(enabled_rules=["SystemStateRule", "IdempotencyRule"])
    await gate.start()
    try:
        decision = await gate.evaluate(_intent())
    finally:
        await gate.shutdown()

    assert decision.reasons[0].metadata["warming_up_remaining_seconds"] > 0


@pytest.mark.asyncio
async def test_after_warming_up_routes_to_engine() -> None:
    """spec scenario：暖機期結束後正常處理。"""
    gate, clock, _, _ = _make_gate(enabled_rules=["SystemStateRule", "IdempotencyRule"])
    await gate.start()
    try:
        # 暖機期 30 秒，前進 31 秒
        clock.advance(timedelta(seconds=31))
        decision = await gate.evaluate(_intent())
    finally:
        await gate.shutdown()

    assert decision.verdict == Verdict.APPROVE


@pytest.mark.asyncio
async def test_warming_up_remaining_seconds_decreases() -> None:
    gate, clock, _, _ = _make_gate(enabled_rules=["SystemStateRule"])
    await gate.start()
    try:
        before = gate.warming_up_remaining_seconds()
        clock.advance(timedelta(seconds=10))
        after = gate.warming_up_remaining_seconds()
    finally:
        await gate.shutdown()

    assert before > after
    assert after >= 0


# ===== shutdown =====


@pytest.mark.asyncio
async def test_evaluate_after_shutdown_raises() -> None:
    """spec scenario：shutdown 後不接受新請求。"""
    gate, _, _, _ = _make_gate(enabled_rules=["SystemStateRule"])
    await gate.start()
    await gate.shutdown()
    with pytest.raises(RuntimeError, match="stopped"):
        await gate.evaluate(_intent())


@pytest.mark.asyncio
async def test_start_twice_raises() -> None:
    gate, _, _, _ = _make_gate(enabled_rules=["SystemStateRule"])
    await gate.start()
    try:
        with pytest.raises(RuntimeError, match="already started"):
            await gate.start()
    finally:
        await gate.shutdown()


# ===== ConfigLoaded 事件 =====


@pytest.mark.asyncio
async def test_start_publishes_config_loaded_event_with_params_hash() -> None:
    gate, _, _, received = _make_gate(enabled_rules=["SystemStateRule"])
    await gate.start()
    try:
        config_loaded = [e for e in received if isinstance(e, ConfigLoaded)]
    finally:
        await gate.shutdown()

    assert len(config_loaded) == 1
    assert len(config_loaded[0].params_hash) == 64  # SHA-256 hex


# ===== 規則註冊 =====


@pytest.mark.asyncio
async def test_unknown_rule_in_config_raises() -> None:
    with pytest.raises(ValueError, match="unknown rule"):
        _make_gate(enabled_rules=["NotARealRule"])


@pytest.mark.asyncio
async def test_state_property_reflects_state_machine() -> None:
    gate, _, _, _ = _make_gate(
        enabled_rules=["SystemStateRule"], initial_state="THROTTLED"
    )
    assert gate.state.value == "THROTTLED"


# ===== from_config 端到端 =====


def test_from_config_builds_gate(tmp_path: Path) -> None:
    """from_config 從 YAML 路徑端到端建構 RiskGate。"""
    gate = RiskGate.from_config(
        config_path=DEFAULT_CONFIG,
        total_equity=Decimal("10000"),
        strategy_budgets={"A": Decimal("5000")},
        symbol_caps={"BTCUSDT": Decimal("4000")},
        positions=_FakePositions(),
        market_data=_FakeMarket(),
        config_reader=_FakeConfig(),
    )
    assert gate.is_started is False
    assert gate.config.fsm.thresholds.daily_pnl_kill == -0.07
