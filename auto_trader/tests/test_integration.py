"""端到端整合測試：跨多個元件驗證合作行為。

對應 spec scenarios（綜合）：
- 100 並發 OrderIntent 通過完整 RuleEngine 與 CapitalReserver
- FSM NORMAL → KILL_SWITCH 全程，SystemStateRule 即時反應
- 暖機期完整流程
- 服務重啟讀回狀態
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.config import RiskConfig
from risk.decision import Outcome, Verdict
from risk.events import EmergencyFlattenRequested, Event, StateChanged
from risk.gate import RiskGate
from risk.reservation.ledger import ReservationLedger
from risk.rules.idempotency import IdempotencyRule
from risk.rules.system_state import SystemStateRule
from risk.state.machine import StateMachine
from risk.state.persistence import InMemoryStateStore
from risk.state.states import SystemState
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


def _intent(signal_id: str = "sig", strategy_id: str = "A") -> OrderIntent:
    return OrderIntent(
        strategy_id=strategy_id,
        symbol="BTCUSDT",
        side=Side.BUY,
        qty=Decimal("1"),
        price=Decimal("65000"),
        signal_id=signal_id,
        bar_time=datetime(2026, 5, 10, tzinfo=UTC),
        received_at=datetime(2026, 5, 10, 0, 0, 1, tzinfo=UTC),
    )


def _make_full_gate(
    *,
    initial_state: str | None = None,
    store: InMemoryStateStore | None = None,
) -> tuple[RiskGate, FrozenClock, InMemoryEventPublisher, list[Event]]:
    """建構僅啟用兩條已實作規則（SystemStateRule + IdempotencyRule）的 gate。"""
    config = RiskConfig.from_yaml(DEFAULT_CONFIG)
    config = config.model_copy(
        update={
            "rules": config.rules.model_copy(
                update={"enabled": ["SystemStateRule", "IdempotencyRule"]}
            )
        }
    )

    clock = FrozenClock(initial=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC))
    if store is None:
        store = InMemoryStateStore()
    if initial_state is not None:
        store.save_state(initial_state)

    publisher = InMemoryEventPublisher()
    received: list[Event] = []

    async def capture(e: Event) -> None:
        received.append(e)

    publisher.subscribe(Event, capture)

    ledger = ReservationLedger(
        total_equity=Decimal("100000"),
        strategy_budgets={"A": Decimal("100000")},
        symbol_caps={"BTCUSDT": Decimal("100000")},
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


# ===== 整合測試 1：100 並發通過完整流程 =====


@pytest.mark.asyncio
async def test_100_concurrent_intents_through_full_gate() -> None:
    """100 並發 OrderIntent 通過完整 RuleEngine（unique signal_id）。"""
    gate, clock, _, _ = _make_full_gate()
    await gate.start()
    try:
        clock.advance(timedelta(seconds=31))  # 過暖機

        tasks = [
            gate.evaluate(_intent(signal_id=f"sig_{i}")) for i in range(100)
        ]
        results = await asyncio.gather(*tasks)
    finally:
        await gate.shutdown()

    approves = [d for d in results if d.verdict == Verdict.APPROVE]
    assert len(approves) == 100


# ===== 整合測試 2：FSM 全程 + SystemStateRule 即時反應 =====


@pytest.mark.asyncio
async def test_fsm_kill_switch_blocks_subsequent_evaluations() -> None:
    """FSM 進入 KILL_SWITCH 後，SystemStateRule 即時拒絕後續訊號。"""
    gate, clock, _, received = _make_full_gate()
    await gate.start()
    try:
        clock.advance(timedelta(seconds=31))  # 過暖機

        # 第一筆通過（NORMAL）
        first = await gate.evaluate(_intent(signal_id="before_kill"))
        assert first.verdict == Verdict.APPROVE

        # FSM tick：PnL -8% → KILL_SWITCH
        await gate.state_machine.tick(daily_pnl_ratio=-0.08, api_error_rate=0.0)
        assert gate.state == SystemState.KILL_SWITCH

        # 第二筆被 SystemStateRule 拒
        second = await gate.evaluate(_intent(signal_id="after_kill"))
        assert second.verdict == Verdict.REJECT
        assert any(r.rule_name == "SystemStateRule" for r in second.reasons)
    finally:
        await gate.shutdown()

    assert any(isinstance(e, EmergencyFlattenRequested) for e in received)


@pytest.mark.asyncio
async def test_fsm_full_progression_with_event_audit() -> None:
    """FSM 完整下行（NORMAL → WARNING → THROTTLED → HALTED → KILL_SWITCH）發出對應事件。"""
    gate, clock, _, received = _make_full_gate()
    await gate.start()
    try:
        clock.advance(timedelta(seconds=31))

        for pnl in [-0.025, -0.035, -0.055, -0.08]:
            await gate.state_machine.tick(daily_pnl_ratio=pnl, api_error_rate=0.0)
    finally:
        await gate.shutdown()

    state_changes = [e for e in received if isinstance(e, StateChanged)]
    transitions = [e.to_state for e in state_changes]
    assert transitions == ["WARNING", "THROTTLED", "HALTED", "KILL_SWITCH"]


# ===== 整合測試 3：暖機期完整流程 =====


@pytest.mark.asyncio
async def test_warming_up_lifecycle_then_normal() -> None:
    """spec scenario 整合：啟動 → 首次 tick → 暖機期拒單 → 暖機結束 → 首筆通過。"""
    gate, clock, _, _ = _make_full_gate()
    await gate.start()
    try:
        # 暖機期內：拒
        warming_up_decision = await gate.evaluate(_intent(signal_id="warming"))
        assert warming_up_decision.verdict == Verdict.REJECT
        assert warming_up_decision.reasons[0].outcome == Outcome.REJECT
        assert warming_up_decision.reasons[0].message == "system_warming_up"

        # 暖機結束（30 秒）
        clock.advance(timedelta(seconds=31))
        ready_decision = await gate.evaluate(_intent(signal_id="ready"))
        assert ready_decision.verdict == Verdict.APPROVE
    finally:
        await gate.shutdown()


# ===== 整合測試 4：服務重啟讀回狀態 =====


@pytest.mark.asyncio
async def test_state_persistence_across_restart() -> None:
    """spec scenario：服務重啟讀回先前狀態（共用 StateStore）。"""
    shared_store = InMemoryStateStore()

    # 第一次啟動：進入 THROTTLED 後關閉
    gate1, _, _, _ = _make_full_gate(store=shared_store)
    await gate1.start()
    try:
        await gate1.state_machine.tick(daily_pnl_ratio=-0.04, api_error_rate=0.0)
        assert gate1.state == SystemState.THROTTLED
    finally:
        await gate1.shutdown()

    # 第二次啟動：應讀回 THROTTLED
    gate2, _, _, _ = _make_full_gate(store=shared_store)
    try:
        assert gate2.state == SystemState.THROTTLED
    finally:
        # 不 start，僅檢查讀回行為
        pass


# ===== 整合測試 5：訊號去重在多筆並發下穩定 =====


@pytest.mark.asyncio
async def test_idempotency_rejects_duplicate_signal_id_in_concurrent_evaluations() -> None:
    gate, clock, _, _ = _make_full_gate()
    await gate.start()
    try:
        clock.advance(timedelta(seconds=31))

        # 同一 signal_id 並發送出 5 次
        tasks = [gate.evaluate(_intent(signal_id="dup")) for _ in range(5)]
        results = await asyncio.gather(*tasks)
    finally:
        await gate.shutdown()

    approves = [r for r in results if r.verdict == Verdict.APPROVE]
    rejects = [r for r in results if r.verdict == Verdict.REJECT]
    # 由於 IdempotencyRule 序列化（在單 actor 與單 engine 串行）：
    # asyncio 是單執行緒，一筆 evaluate 完整執行才到下一筆，故第一筆通過、其餘四筆拒
    assert len(approves) == 1
    assert len(rejects) == 4


# ===== 整合測試 6：SystemStateRule 不依賴 gate 仍可運作（單元式驗證） =====


@pytest.mark.asyncio
async def test_system_state_rule_subscribes_state_machine_directly() -> None:
    """確認 SystemStateRule 與 StateMachine 解耦透過 Event Bus（D-10）。"""
    publisher = InMemoryEventPublisher()
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    store = InMemoryStateStore()

    config = RiskConfig.from_yaml(DEFAULT_CONFIG)
    machine = StateMachine(
        clock=clock,
        store=store,
        publisher=publisher,
        thresholds=config.fsm.thresholds,
        cooling_seconds=config.fsm.thresholds.kill_switch_cooling_seconds,
    )
    rule = SystemStateRule(initial_state=machine.state.value, publisher=publisher)

    # Initial NORMAL
    assert rule.current_state == "NORMAL"

    # 透過 machine 推進 → rule 收到事件更新
    await machine.tick(daily_pnl_ratio=-0.08, api_error_rate=0.0)
    assert machine.state == SystemState.KILL_SWITCH
    assert rule.current_state == "KILL_SWITCH"


# ===== 整合測試 7：IdempotencyRule TTL 與 Clock 同步 =====


@pytest.mark.asyncio
async def test_idempotency_ttl_uses_injected_clock() -> None:
    """IdempotencyRule 的 TTL 計算依注入的 Clock，可被 FrozenClock 控制。"""
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    rule = IdempotencyRule(clock=clock, ttl_seconds=300)

    from risk.rules.base import RuleContext

    def _ctx(sid: str) -> RuleContext:
        return RuleContext(
            intent=_intent(signal_id=sid),
            current_size=Decimal("1"),
            current_price=None,
            positions=_FakePositions(),
            market_data=_FakeMarket(),
            config=_FakeConfig(),
            clock=clock,
        )

    rule.evaluate(_ctx("a"))
    clock.advance(timedelta(seconds=299))
    second = rule.evaluate(_ctx("a"))
    assert second.outcome == Outcome.REJECT

    clock.advance(timedelta(seconds=2))
    third = rule.evaluate(_ctx("a"))
    assert third.outcome == Outcome.PASS
