"""order-execution capability 完整測試（含 events / sink / mock / stub / config）。"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from execution.adapters.ccxt_stub import CcxtExecutionAdapter
from execution.adapters.mock import MockExecutionAdapter
from execution.config import ExecutionConfig
from execution.events import OrderRejectedByBroker, OrderSubmitted
from execution.ports import ExecutionAdapter
from execution.sink import ExchangeOrderSink
from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.decision import Decision, Verdict
from risk.events import Event
from risk.types import OrderIntent, Side
from strategies.ports import OrderSink
from tests.fakes.frozen_clock import FrozenClock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_YAML = PROJECT_ROOT / "config" / "execution.yaml"


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


def _decision() -> Decision:
    return Decision(
        verdict=Verdict.APPROVE,
        final_size=Decimal("1"),
        final_price=Decimal("65000"),
        reasons=[],
        reservation_id=None,
        evaluated_at=datetime(2026, 5, 10, tzinfo=UTC),
    )


# ===== ExecutionAdapter Protocol =====


def test_mock_satisfies_execution_adapter_protocol() -> None:
    assert isinstance(MockExecutionAdapter(), ExecutionAdapter)


def test_ccxt_stub_satisfies_execution_adapter_protocol() -> None:
    assert isinstance(CcxtExecutionAdapter(), ExecutionAdapter)


@pytest.mark.asyncio
async def test_ccxt_stub_submit_raises_not_implemented() -> None:
    adapter = CcxtExecutionAdapter()
    with pytest.raises(NotImplementedError, match="not implemented"):
        await adapter.submit(intent=_intent(), client_order_id="A.x.1")


@pytest.mark.asyncio
async def test_ccxt_stub_cancel_raises_not_implemented() -> None:
    adapter = CcxtExecutionAdapter()
    with pytest.raises(NotImplementedError):
        await adapter.cancel("bo-1")


# ===== MockExecutionAdapter =====


@pytest.mark.asyncio
async def test_mock_submit_default_returns_unique_ids() -> None:
    """spec scenario：預設成功模式 submit 回傳 broker_order_id。"""
    mock = MockExecutionAdapter()
    a = await mock.submit(intent=_intent(), client_order_id="A.x.1")
    b = await mock.submit(intent=_intent(), client_order_id="A.x.2")
    assert a != b
    assert len(mock.submitted) == 2


@pytest.mark.asyncio
async def test_mock_fail_next_raises() -> None:
    """spec scenario：failure_mode 啟用後 submit 拋例外。"""
    mock = MockExecutionAdapter()
    mock.fail_next = True
    with pytest.raises(RuntimeError):
        await mock.submit(intent=_intent(), client_order_id="A.x.1")
    # 紀錄仍寫入（含 error 標記）
    assert mock.submitted[-1].error is not None


@pytest.mark.asyncio
async def test_mock_records_all_submits() -> None:
    """spec scenario：紀錄所有 submit 呼叫。"""
    mock = MockExecutionAdapter()
    await mock.submit(intent=_intent(), client_order_id="A.x.1")
    await mock.submit(intent=_intent(), client_order_id="A.x.2")
    await mock.submit(intent=_intent(), client_order_id="A.x.3")
    assert len(mock.submitted) == 3


@pytest.mark.asyncio
async def test_mock_cancel_records() -> None:
    mock = MockExecutionAdapter()
    await mock.cancel("bo-1")
    await mock.cancel("bo-2")
    assert mock.canceled == ["bo-1", "bo-2"]


# ===== ExchangeOrderSink =====


def _make_sink() -> tuple[ExchangeOrderSink, MockExecutionAdapter, list[Event]]:
    mock = MockExecutionAdapter()
    publisher = InMemoryEventPublisher()
    received: list[Event] = []

    async def capture(e: Event) -> None:
        received.append(e)

    publisher.subscribe(Event, capture)

    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    sink = ExchangeOrderSink(adapter=mock, publisher=publisher, clock=clock)
    return sink, mock, received


@pytest.mark.asyncio
async def test_sink_satisfies_order_sink_protocol() -> None:
    """spec scenario：ExchangeOrderSink 結構符合 strategies.ports.OrderSink。"""
    sink, _, _ = _make_sink()
    assert isinstance(sink, OrderSink)


@pytest.mark.asyncio
async def test_sink_success_emits_order_submitted() -> None:
    """spec scenario：成功 submit 發布 OrderSubmitted。"""
    sink, _mock, received = _make_sink()
    broker_id = await sink.submit(
        intent=_intent(),
        decision=_decision(),
        client_order_id="A.abc.1",
    )
    assert broker_id.startswith("mock-")
    submitted = [e for e in received if isinstance(e, OrderSubmitted)]
    assert len(submitted) == 1
    assert submitted[0].client_order_id == "A.abc.1"
    assert submitted[0].broker_order_id == broker_id


@pytest.mark.asyncio
async def test_sink_failure_emits_rejected_and_reraises() -> None:
    """spec scenario：adapter 失敗發布 OrderRejectedByBroker + re-raise。"""
    sink, mock, received = _make_sink()
    mock.fail_next = True
    with pytest.raises(RuntimeError):
        await sink.submit(
            intent=_intent(),
            decision=_decision(),
            client_order_id="A.abc.1",
        )
    rejected = [e for e in received if isinstance(e, OrderRejectedByBroker)]
    assert len(rejected) == 1
    assert "intentional failure" in rejected[0].reason


# ===== Events =====


def test_order_submitted_immutable() -> None:
    e = OrderSubmitted(
        at=datetime(2026, 5, 10, tzinfo=UTC),
        client_order_id="A.x.1",
        broker_order_id="bo-1",
        symbol="BTCUSDT",
        strategy_id="A",
    )
    with pytest.raises(FrozenInstanceError):
        e.broker_order_id = "bo-2"  # type: ignore[misc]


def test_order_submitted_serializable() -> None:
    e = OrderSubmitted(
        at=datetime(2026, 5, 10, tzinfo=UTC),
        client_order_id="A.x.1",
        broker_order_id="bo-1",
        symbol="BTCUSDT",
        strategy_id="A",
    )
    encoded = json.dumps(e.to_dict())
    decoded = json.loads(encoded)
    assert decoded["broker_order_id"] == "bo-1"
    assert decoded["strategy_id"] == "A"


def test_order_rejected_serializable() -> None:
    e = OrderRejectedByBroker(
        at=datetime(2026, 5, 10, tzinfo=UTC),
        client_order_id="A.x.1",
        symbol="BTCUSDT",
        strategy_id="A",
        reason="insufficient balance",
    )
    encoded = json.dumps(e.to_dict())
    decoded = json.loads(encoded)
    assert decoded["reason"] == "insufficient balance"


# ===== Config =====


def test_default_yaml_loads() -> None:
    cfg = ExecutionConfig.from_yaml(DEFAULT_YAML)
    assert cfg.broker == "mock"
    assert cfg.testnet is True


def test_config_extra_forbidden(tmp_path: Path) -> None:
    p = tmp_path / "x.yaml"
    p.write_text(
        yaml.safe_dump({"broker": "mock", "extra_field": "x"}), encoding="utf-8"
    )
    with pytest.raises(ValidationError):
        ExecutionConfig.from_yaml(p)


def test_config_root_must_be_mapping(tmp_path: Path) -> None:
    p = tmp_path / "x.yaml"
    p.write_text("- a\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        ExecutionConfig.from_yaml(p)


# ===== e2e 整合：StrategyHost + ExchangeOrderSink + MockExecutionAdapter =====


@pytest.mark.asyncio
async def test_e2e_strategy_host_with_exchange_sink() -> None:
    """端到端：strategy-host 透過 ExchangeOrderSink + MockExecutionAdapter 完整下單。"""
    from datetime import timedelta

    from risk.config import RiskConfig
    from risk.gate import RiskGate
    from risk.reservation.ledger import ReservationLedger
    from risk.state.persistence import InMemoryStateStore
    from signals.types import SCHEMA_VERSION_CURRENT, Signal, SignalSourceKind
    from strategies.host import StrategyHost
    from strategies.registry import StrategyRegistry
    from strategies.strategies.passthrough import PassthroughStrategy
    from strategies.types import StrategyState

    config = RiskConfig.from_yaml(PROJECT_ROOT / "config" / "risk.yaml")
    config = config.model_copy(
        update={
            "rules": config.rules.model_copy(
                update={"enabled": ["SystemStateRule", "IdempotencyRule"]}
            )
        }
    )
    clock = FrozenClock(initial=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC))

    class _FP:
        def get_position(self, sid: str, sym: str) -> Any:
            return None

        def list_positions(self) -> list[Any]:
            return []

    class _FM:
        def get_last_price(self, s: str) -> Decimal:
            return Decimal("65000")

    class _FC:
        def get(self, k: str) -> Any:
            return None

    publisher = InMemoryEventPublisher()
    received: list[Event] = []

    async def capture(e: Event) -> None:
        received.append(e)

    publisher.subscribe(Event, capture)

    risk_gate = RiskGate(
        config=config,
        clock=clock,
        store=InMemoryStateStore(),
        publisher=publisher,
        positions=_FP(),
        market_data=_FM(),
        config_reader=_FC(),
        ledger=ReservationLedger(
            total_equity=Decimal("100000"),
            strategy_budgets={"A": Decimal("100000")},
            symbol_caps={"BTCUSDT": Decimal("100000")},
        ),
    )

    mock_adapter = MockExecutionAdapter()
    sink = ExchangeOrderSink(adapter=mock_adapter, publisher=publisher, clock=clock)

    registry = StrategyRegistry()
    strategy = PassthroughStrategy(
        strategy_id="A", strategy_version="1.0.0", params_hash="hash"
    )
    registry.register(strategy)
    registry.set_state("A", StrategyState.ACTIVE)

    host = StrategyHost(registry=registry, risk_gate=risk_gate, order_sink=sink)

    signal = Signal(
        schema_version=SCHEMA_VERSION_CURRENT,
        signal_id="abc123def456000000000000000",
        strategy_id="A",
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

    await risk_gate.start()
    try:
        clock.advance(timedelta(seconds=31))
        await host.on_signal(signal)
    finally:
        await risk_gate.shutdown()

    # 應有一筆訂單透過 mock adapter 出去
    assert len(mock_adapter.submitted) == 1
    assert mock_adapter.submitted[0].broker_order_id == "mock-1"

    # 應發布 OrderSubmitted 事件
    submitted = [e for e in received if isinstance(e, OrderSubmitted)]
    assert len(submitted) == 1
    assert submitted[0].broker_order_id == "mock-1"
