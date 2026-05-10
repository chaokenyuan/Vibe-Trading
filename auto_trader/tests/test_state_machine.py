"""StateMachine + transitions + persistence 單元測試。

對應 spec scenarios：
- 服務首次啟動使用預設狀態 / 服務重啟讀回先前狀態 / 不可越級回升
- PnL 跌破 -2% 進入 WARNING / 跌破 -5% 直接進入 HALTED
- WARNING 條件解除自動回升 NORMAL / HALTED 不自動回升
- HALTED 接受人工 reset / KILL_SWITCH 觸發自動全平請求
- KILL_SWITCH 冷靜期內拒絕 reset / 冷靜期後接受 reset
- 人工進入維護模式
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.config import FsmThresholds
from risk.events import EmergencyFlattenRequested, Event, StateChanged
from risk.state.machine import StateMachine
from risk.state.persistence import InMemoryStateStore
from risk.state.states import SystemState
from risk.state.transitions import evaluate_transition
from tests.fakes.frozen_clock import FrozenClock


def _thresholds() -> FsmThresholds:
    return FsmThresholds(
        daily_pnl_warning=-0.02,
        daily_pnl_throttled=-0.03,
        daily_pnl_halted=-0.05,
        daily_pnl_kill=-0.07,
        api_error_rate_throttled=0.05,
        kill_switch_cooling_seconds=14400,
    )


def _make_machine(
    *,
    initial_state: SystemState | None = None,
    cooling_seconds: int = 14400,
) -> tuple[StateMachine, FrozenClock, InMemoryEventPublisher, InMemoryStateStore, list[Event]]:
    clock = FrozenClock(initial=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC))
    store = InMemoryStateStore()
    if initial_state is not None:
        store.save_state(initial_state.value)
    publisher = InMemoryEventPublisher()
    received: list[Event] = []

    async def capture(e: Event) -> None:
        received.append(e)

    publisher.subscribe(Event, capture)

    machine = StateMachine(
        clock=clock,
        store=store,
        publisher=publisher,
        thresholds=_thresholds(),
        cooling_seconds=cooling_seconds,
    )
    return machine, clock, publisher, store, received


# ===== 純函式 transitions 測試 =====


def test_transition_normal_to_warning_at_minus_2_pct() -> None:
    target = evaluate_transition(
        SystemState.NORMAL,
        daily_pnl_ratio=-0.023,
        api_error_rate=0.0,
        thresholds=_thresholds(),
    )
    assert target == SystemState.WARNING


def test_transition_warning_to_halted_skipping_throttled() -> None:
    """spec scenario：PnL 跌破 -5% 直接進入 HALTED（跨級下行）。"""
    target = evaluate_transition(
        SystemState.WARNING,
        daily_pnl_ratio=-0.055,
        api_error_rate=0.0,
        thresholds=_thresholds(),
    )
    assert target == SystemState.HALTED


def test_transition_pnl_below_kill_threshold_to_kill_switch() -> None:
    target = evaluate_transition(
        SystemState.NORMAL,
        daily_pnl_ratio=-0.08,
        api_error_rate=0.0,
        thresholds=_thresholds(),
    )
    assert target == SystemState.KILL_SWITCH


def test_transition_warning_back_to_normal_when_pnl_recovers() -> None:
    """spec scenario：WARNING 條件解除自動回升 NORMAL。"""
    target = evaluate_transition(
        SystemState.WARNING,
        daily_pnl_ratio=0.005,
        api_error_rate=0.0,
        thresholds=_thresholds(),
    )
    assert target == SystemState.NORMAL


def test_transition_halted_does_not_auto_recover() -> None:
    """spec scenario：HALTED 不自動回升。"""
    target = evaluate_transition(
        SystemState.HALTED,
        daily_pnl_ratio=0.005,
        api_error_rate=0.0,
        thresholds=_thresholds(),
    )
    assert target == SystemState.HALTED


def test_transition_kill_switch_does_not_auto_recover() -> None:
    target = evaluate_transition(
        SystemState.KILL_SWITCH,
        daily_pnl_ratio=0.005,
        api_error_rate=0.0,
        thresholds=_thresholds(),
    )
    assert target == SystemState.KILL_SWITCH


def test_transition_throttled_steps_up_to_warning_not_normal() -> None:
    """上行階梯：THROTTLED → WARNING（不跳級到 NORMAL）。"""
    target = evaluate_transition(
        SystemState.THROTTLED,
        daily_pnl_ratio=0.005,
        api_error_rate=0.0,
        thresholds=_thresholds(),
    )
    assert target == SystemState.WARNING


def test_transition_api_error_alone_triggers_throttled() -> None:
    target = evaluate_transition(
        SystemState.NORMAL,
        daily_pnl_ratio=0.0,
        api_error_rate=0.06,
        thresholds=_thresholds(),
    )
    assert target == SystemState.THROTTLED


def test_transition_maintenance_unaffected_by_metrics() -> None:
    target = evaluate_transition(
        SystemState.MAINTENANCE,
        daily_pnl_ratio=-0.10,
        api_error_rate=0.5,
        thresholds=_thresholds(),
    )
    assert target == SystemState.MAINTENANCE


# ===== StateMachine 啟動讀回 =====


def test_first_startup_defaults_to_normal() -> None:
    machine, *_ = _make_machine()
    assert machine.state == SystemState.NORMAL


def test_restart_loads_previous_state_throttled() -> None:
    """spec scenario：服務重啟讀回先前狀態為 THROTTLED。"""
    machine, *_ = _make_machine(initial_state=SystemState.THROTTLED)
    assert machine.state == SystemState.THROTTLED


# ===== StateMachine.tick 自動轉換 =====


@pytest.mark.asyncio
async def test_tick_normal_to_warning_publishes_event() -> None:
    machine, _clock, _, _, received = _make_machine()
    await machine.tick(daily_pnl_ratio=-0.023, api_error_rate=0.0)
    assert machine.state == SystemState.WARNING
    state_changes = [e for e in received if isinstance(e, StateChanged)]
    assert len(state_changes) == 1
    assert state_changes[0].from_state == "NORMAL"
    assert state_changes[0].to_state == "WARNING"


@pytest.mark.asyncio
async def test_tick_no_change_does_not_publish() -> None:
    machine, _, _, _, received = _make_machine()
    await machine.tick(daily_pnl_ratio=0.0, api_error_rate=0.0)
    assert machine.state == SystemState.NORMAL
    assert [e for e in received if isinstance(e, StateChanged)] == []


@pytest.mark.asyncio
async def test_tick_persists_state_change() -> None:
    machine, _, _, store, _ = _make_machine()
    await machine.tick(daily_pnl_ratio=-0.04, api_error_rate=0.0)
    assert machine.state == SystemState.THROTTLED
    assert store.load_state() == "THROTTLED"


# ===== KILL_SWITCH 與全平 =====


@pytest.mark.asyncio
async def test_kill_switch_triggers_emergency_flatten_event() -> None:
    """spec scenario：KILL_SWITCH 觸發自動全平請求。"""
    machine, _, _, _, received = _make_machine()
    await machine.tick(daily_pnl_ratio=-0.10, api_error_rate=0.0)
    assert machine.state == SystemState.KILL_SWITCH
    assert any(isinstance(e, EmergencyFlattenRequested) for e in received)


@pytest.mark.asyncio
async def test_kill_switch_publishes_state_changed_then_flatten() -> None:
    """spec scenario：KILL_SWITCH 同時觸發兩個事件（state + flatten）。"""
    machine, _, _, _, received = _make_machine()
    await machine.tick(daily_pnl_ratio=-0.10, api_error_rate=0.0)
    types = [type(e).__name__ for e in received]
    assert "StateChanged" in types
    assert "EmergencyFlattenRequested" in types
    # 且 StateChanged 在 EmergencyFlattenRequested 之前
    assert types.index("StateChanged") < types.index("EmergencyFlattenRequested")


# ===== 人工 reset =====


@pytest.mark.asyncio
async def test_manual_reset_from_halted_succeeds() -> None:
    """spec scenario：HALTED 接受人工 reset。"""
    machine, *_ = _make_machine(initial_state=SystemState.HALTED)
    result = await machine.reset()
    assert result.ok is True
    assert machine.state == SystemState.NORMAL


@pytest.mark.asyncio
async def test_kill_switch_reset_within_cooling_rejected() -> None:
    """spec scenario：KILL_SWITCH 冷靜期內拒絕 reset。"""
    machine, clock, _, _, _ = _make_machine(cooling_seconds=14400)
    # 進入 KILL_SWITCH
    await machine.tick(daily_pnl_ratio=-0.10, api_error_rate=0.0)
    assert machine.state == SystemState.KILL_SWITCH

    # 2 小時後（仍在冷靜期）
    clock.advance(timedelta(hours=2))
    result = await machine.reset()
    assert result.ok is False
    assert result.cooling_remaining_seconds is not None
    assert result.cooling_remaining_seconds > 0
    assert machine.state == SystemState.KILL_SWITCH


@pytest.mark.asyncio
async def test_kill_switch_reset_after_cooling_succeeds() -> None:
    """spec scenario：KILL_SWITCH 冷靜期後接受 reset。"""
    machine, clock, _, _, _ = _make_machine(cooling_seconds=14400)
    await machine.tick(daily_pnl_ratio=-0.10, api_error_rate=0.0)

    # 4 小時 1 秒後（已過冷靜期）
    clock.advance(timedelta(hours=4, seconds=1))
    result = await machine.reset()
    assert result.ok is True
    assert machine.state == SystemState.NORMAL


# ===== MAINTENANCE 人工指令 =====


@pytest.mark.asyncio
async def test_enter_maintenance_from_any_state() -> None:
    """spec scenario：人工進入維護模式。"""
    machine, *_ = _make_machine(initial_state=SystemState.WARNING)
    await machine.enter_maintenance()
    assert machine.state == SystemState.MAINTENANCE


@pytest.mark.asyncio
async def test_exit_maintenance_only_from_maintenance() -> None:
    machine, *_ = _make_machine(initial_state=SystemState.NORMAL)
    with pytest.raises(RuntimeError, match="MAINTENANCE"):
        await machine.exit_maintenance()


@pytest.mark.asyncio
async def test_exit_maintenance_to_normal() -> None:
    machine, *_ = _make_machine(initial_state=SystemState.MAINTENANCE)
    await machine.exit_maintenance()
    assert machine.state == SystemState.NORMAL


@pytest.mark.asyncio
async def test_maintenance_unaffected_by_tick() -> None:
    machine, *_ = _make_machine(initial_state=SystemState.MAINTENANCE)
    await machine.tick(daily_pnl_ratio=-0.10, api_error_rate=0.5)
    assert machine.state == SystemState.MAINTENANCE
