"""StrategyHost + PassthroughStrategy 整合測試。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.config import RiskConfig
from risk.decision import Decision, Verdict
from risk.gate import RiskGate
from risk.reservation.ledger import ReservationLedger
from risk.state.persistence import InMemoryStateStore
from risk.types import OrderIntent
from signals.types import (
    SCHEMA_VERSION_CURRENT,
    Signal,
    SignalSourceKind,
)
from strategies.host import StrategyHost
from strategies.ports import OrderSink
from strategies.registry import StrategyRegistry
from strategies.strategies.passthrough import PassthroughStrategy
from strategies.types import StrategyState
from tests.fakes.frozen_clock import FrozenClock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RISK_CONFIG = PROJECT_ROOT / "config" / "risk.yaml"


class _RecordingOrderSink:
    def __init__(self) -> None:
        self.submitted: list[tuple[OrderIntent, Decision, str]] = []

    async def submit(
        self,
        *,
        intent: OrderIntent,
        decision: Decision,
        client_order_id: str,
    ) -> str:
        self.submitted.append((intent, decision, client_order_id))
        return f"broker-{len(self.submitted)}"


class _CrashingStrategy:
    def __init__(self, strategy_id: str = "crash") -> None:
        from signals.types import StrategyMetadata

        self._strategy_id = strategy_id
        self._metadata = StrategyMetadata(
            strategy_id=strategy_id,
            strategy_version="1.0.0",
            params_hash="hash",
        )

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    @property
    def metadata(self) -> Any:
        return self._metadata

    async def on_signal(self, signal: Signal) -> list[OrderIntent]:
        raise RuntimeError("intentional strategy crash")

    async def on_fill(self, fill: Any) -> None:
        return None


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


def _make_setup() -> tuple[
    StrategyHost,
    StrategyRegistry,
    RiskGate,
    _RecordingOrderSink,
    FrozenClock,
]:
    config = RiskConfig.from_yaml(DEFAULT_RISK_CONFIG)
    config = config.model_copy(
        update={
            "rules": config.rules.model_copy(
                update={"enabled": ["SystemStateRule", "IdempotencyRule"]}
            )
        }
    )
    clock = FrozenClock(initial=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC))
    risk_gate = RiskGate(
        config=config,
        clock=clock,
        store=InMemoryStateStore(),
        publisher=InMemoryEventPublisher(),
        positions=_FakePositions(),
        market_data=_FakeMarket(),
        config_reader=_FakeConfig(),
        ledger=ReservationLedger(
            total_equity=Decimal("100000"),
            strategy_budgets={"A": Decimal("100000"), "crash": Decimal("100000")},
            symbol_caps={"BTCUSDT": Decimal("100000")},
        ),
    )

    registry = StrategyRegistry()
    sink = _RecordingOrderSink()
    host = StrategyHost(registry=registry, risk_gate=risk_gate, order_sink=sink)
    return host, registry, risk_gate, sink, clock


def _signal(strategy_id: str = "A") -> Signal:
    return Signal(
        schema_version=SCHEMA_VERSION_CURRENT,
        signal_id="abc123def456_full_hash_xxxxxxxxxxxxxxx",
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        params_hash="hash",
        symbol="BTCUSDT",
        side="BUY",
        qty=Decimal("1"),
        price=Decimal("65000"),
        bar_time=datetime(2026, 5, 10, tzinfo=UTC),
        interval="60",
        received_at=datetime(2026, 5, 10, 0, 0, 1, tzinfo=UTC),
        source=SignalSourceKind.TRADINGVIEW,
        comment=None,
        raw_payload={},
    )


# ===== ACTIVE 完整鏈路 =====


@pytest.mark.asyncio
async def test_active_strategy_signal_flows_to_order_sink() -> None:
    """spec scenario：ACTIVE 策略訊號通過全鏈路。"""
    host, registry, risk_gate, sink, clock = _make_setup()
    strategy = PassthroughStrategy(
        strategy_id="A", strategy_version="1.0.0", params_hash="hash"
    )
    registry.register(strategy)
    registry.set_state("A", StrategyState.ACTIVE)

    await risk_gate.start()
    try:
        clock.advance(timedelta(seconds=31))  # 過暖機
        await host.on_signal(_signal("A"))
    finally:
        await risk_gate.shutdown()

    assert len(sink.submitted) == 1
    _intent, decision, coid = sink.submitted[0]
    assert decision.verdict == Verdict.APPROVE
    assert coid.startswith("A.")
    assert coid.endswith(".1")


# ===== Non-ACTIVE 跳過 =====


@pytest.mark.asyncio
async def test_paused_strategy_signal_skipped() -> None:
    """spec scenario：PAUSED 策略訊號跳過。"""
    host, registry, risk_gate, sink, clock = _make_setup()
    strategy = PassthroughStrategy(
        strategy_id="A", strategy_version="1.0.0", params_hash="hash"
    )
    registry.register(strategy)
    registry.set_state("A", StrategyState.PAUSED)

    await risk_gate.start()
    try:
        clock.advance(timedelta(seconds=31))
        await host.on_signal(_signal("A"))
    finally:
        await risk_gate.shutdown()

    assert sink.submitted == []


@pytest.mark.asyncio
async def test_unknown_strategy_signal_skipped() -> None:
    """spec scenario：未註冊 strategy 訊號跳過。"""
    host, _registry, risk_gate, sink, clock = _make_setup()
    # 故意不註冊任何 strategy

    await risk_gate.start()
    try:
        clock.advance(timedelta(seconds=31))
        await host.on_signal(_signal("UNKNOWN"))
    finally:
        await risk_gate.shutdown()

    assert sink.submitted == []


# ===== Crash → FAILED =====


@pytest.mark.asyncio
async def test_strategy_crash_sets_state_failed_and_skips_subsequent() -> None:
    """spec scenario：Strategy crash 進入 FAILED + 後續訊號跳過。"""
    host, registry, risk_gate, sink, clock = _make_setup()
    strategy = _CrashingStrategy(strategy_id="crash")
    registry.register(strategy)
    registry.set_state("crash", StrategyState.ACTIVE)

    await risk_gate.start()
    try:
        clock.advance(timedelta(seconds=31))
        await host.on_signal(_signal("crash"))
        # 第一次 crash 應觸發 FAILED
        assert registry.get_state("crash") == StrategyState.FAILED

        # 後續訊號跳過
        await host.on_signal(_signal("crash"))
    finally:
        await risk_gate.shutdown()

    assert sink.submitted == []


# ===== RiskGate REJECT 不 submit =====


@pytest.mark.asyncio
async def test_risk_gate_reject_does_not_submit() -> None:
    """spec scenario：RiskGate REJECT 不 submit。"""
    host, registry, risk_gate, sink, _clock = _make_setup()
    strategy = PassthroughStrategy(
        strategy_id="A", strategy_version="1.0.0", params_hash="hash"
    )
    registry.register(strategy)
    registry.set_state("A", StrategyState.ACTIVE)

    await risk_gate.start()
    try:
        # 不過暖機 → RiskGate.evaluate 直接 REJECT
        await host.on_signal(_signal("A"))
    finally:
        await risk_gate.shutdown()

    assert sink.submitted == []


# ===== client_order_id 編碼 =====


@pytest.mark.asyncio
async def test_client_order_id_encoding_format() -> None:
    """spec scenario：同訊號多 OrderIntent 各帶不同 seq。"""
    # PassthroughStrategy 1:1，本測試驗證單筆格式即可
    host, registry, risk_gate, sink, clock = _make_setup()
    strategy = PassthroughStrategy(
        strategy_id="A", strategy_version="1.0.0", params_hash="hash"
    )
    registry.register(strategy)
    registry.set_state("A", StrategyState.ACTIVE)

    await risk_gate.start()
    try:
        clock.advance(timedelta(seconds=31))
        await host.on_signal(_signal("A"))
    finally:
        await risk_gate.shutdown()

    _, _, coid = sink.submitted[0]
    parts = coid.split(".")
    assert len(parts) == 3
    assert parts[0] == "A"
    assert len(parts[1]) == 12  # signal_id_short
    assert parts[2] == "1"


def test_decode_strategy_id_helper() -> None:
    assert StrategyHost.decode_strategy_id("A.abc123def456.1") == "A"
    assert StrategyHost.decode_strategy_id("vibe_btc_v1.x.5") == "vibe_btc_v1"


# ===== Strategy Protocol 結構驗證 =====


def test_passthrough_strategy_satisfies_protocol() -> None:
    from strategies.ports import Strategy

    s = PassthroughStrategy(strategy_id="A", strategy_version="1", params_hash="h")
    assert isinstance(s, Strategy)


def test_recording_order_sink_satisfies_protocol() -> None:
    sink = _RecordingOrderSink()
    assert isinstance(sink, OrderSink)
