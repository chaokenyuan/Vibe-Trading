"""StateMachine 整合測試：FrozenClock 模擬一日完整 tick 序列 + start/stop 循環。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.config import FsmThresholds
from risk.events import EmergencyFlattenRequested, Event, StateChanged
from risk.state.machine import StateMachine
from risk.state.persistence import InMemoryStateStore
from risk.state.states import SystemState
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


@pytest.mark.asyncio
async def test_full_day_simulation_normal_to_kill_switch() -> None:
    """模擬：NORMAL → WARNING → THROTTLED → HALTED → KILL_SWITCH。

    驗證所有轉換都產生事件，且事件順序合理。
    """
    clock = FrozenClock(initial=datetime(2026, 5, 10, 9, 0, 0, tzinfo=UTC))
    store = InMemoryStateStore()
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
        cooling_seconds=14400,
    )

    # 收集每階段後的狀態，最後一次比對（避免 mypy 在連續 assert 上做 literal narrowing）
    timeline: list[SystemState] = [machine.state]

    clock.advance(timedelta(hours=1))
    await machine.tick(daily_pnl_ratio=-0.025, api_error_rate=0.0)
    timeline.append(machine.state)

    clock.advance(timedelta(hours=1))
    await machine.tick(daily_pnl_ratio=-0.035, api_error_rate=0.0)
    timeline.append(machine.state)

    clock.advance(timedelta(hours=1))
    await machine.tick(daily_pnl_ratio=-0.055, api_error_rate=0.0)
    timeline.append(machine.state)

    clock.advance(timedelta(hours=1))
    await machine.tick(daily_pnl_ratio=-0.08, api_error_rate=0.0)
    timeline.append(machine.state)

    assert timeline == [
        SystemState.NORMAL,
        SystemState.WARNING,
        SystemState.THROTTLED,
        SystemState.HALTED,
        SystemState.KILL_SWITCH,
    ]

    # 驗證事件序列
    state_changes = [e for e in received if isinstance(e, StateChanged)]
    assert [e.to_state for e in state_changes] == [
        "WARNING",
        "THROTTLED",
        "HALTED",
        "KILL_SWITCH",
    ]
    # 最後一個轉換有 EmergencyFlattenRequested
    assert any(isinstance(e, EmergencyFlattenRequested) for e in received)


@pytest.mark.asyncio
async def test_recovery_step_up_through_levels() -> None:
    """模擬條件改善：THROTTLED → WARNING → NORMAL（每 tick 升一級）。"""
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    store = InMemoryStateStore()
    store.save_state(SystemState.THROTTLED.value)
    publisher = InMemoryEventPublisher()

    machine = StateMachine(
        clock=clock,
        store=store,
        publisher=publisher,
        thresholds=_thresholds(),
        cooling_seconds=14400,
    )

    timeline: list[SystemState] = [machine.state]

    # 條件全清 + tick → 應升級至 WARNING（不直接到 NORMAL）
    await machine.tick(daily_pnl_ratio=0.01, api_error_rate=0.0)
    timeline.append(machine.state)

    # 再一 tick → NORMAL
    await machine.tick(daily_pnl_ratio=0.01, api_error_rate=0.0)
    timeline.append(machine.state)

    assert timeline == [SystemState.THROTTLED, SystemState.WARNING, SystemState.NORMAL]


@pytest.mark.asyncio
async def test_start_executes_first_tick_immediately() -> None:
    """spec scenario：啟動後立即執行 tick，不等 60 秒週期。"""
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    store = InMemoryStateStore()
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
        cooling_seconds=14400,
        tick_interval_seconds=60,
    )

    metrics_calls = 0

    async def metrics() -> tuple[float, float]:
        nonlocal metrics_calls
        metrics_calls += 1
        return (-0.025, 0.0)  # 觸發 WARNING

    await machine.start(metrics)
    # 給事件循環一個機會跑首次 tick
    await asyncio.sleep(0.05)

    assert metrics_calls >= 1
    assert machine.state == SystemState.WARNING

    await machine.stop()


@pytest.mark.asyncio
async def test_start_twice_raises() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    store = InMemoryStateStore()
    publisher = InMemoryEventPublisher()
    machine = StateMachine(
        clock=clock,
        store=store,
        publisher=publisher,
        thresholds=_thresholds(),
        cooling_seconds=14400,
    )

    async def metrics() -> tuple[float, float]:
        return (0.0, 0.0)

    await machine.start(metrics)
    try:
        with pytest.raises(RuntimeError, match="already started"):
            await machine.start(metrics)
    finally:
        await machine.stop()


@pytest.mark.asyncio
async def test_metrics_provider_failure_does_not_crash_loop() -> None:
    """metrics_provider 拋例外時，loop 不應掛掉（容錯）。"""
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    store = InMemoryStateStore()
    publisher = InMemoryEventPublisher()
    machine = StateMachine(
        clock=clock,
        store=store,
        publisher=publisher,
        thresholds=_thresholds(),
        cooling_seconds=14400,
        tick_interval_seconds=60,
    )

    async def failing_metrics() -> tuple[float, float]:
        raise RuntimeError("metrics service down")

    await machine.start(failing_metrics)
    await asyncio.sleep(0.05)
    # 應仍在 NORMAL 且不拋例外
    assert machine.state == SystemState.NORMAL
    await machine.stop()


@pytest.mark.asyncio
async def test_stop_is_idempotent() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    store = InMemoryStateStore()
    publisher = InMemoryEventPublisher()
    machine = StateMachine(
        clock=clock,
        store=store,
        publisher=publisher,
        thresholds=_thresholds(),
        cooling_seconds=14400,
    )

    # 未啟動就 stop 不應拋
    await machine.stop()

    async def metrics() -> tuple[float, float]:
        return (0.0, 0.0)

    await machine.start(metrics)
    await machine.stop()
    # 第二次 stop 不應拋
    await machine.stop()
