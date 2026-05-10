"""DailyPnlTracker 跨日重置測試。

對應 spec scenario：跨日重置依配置時區（UTC 0:00 觸發 DailyPnlReset 事件 + 計數器歸零）。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.events import DailyPnlReset, Event
from risk.state.daily_pnl import DailyPnlTracker
from tests.fakes.frozen_clock import FrozenClock


def _make_tracker(
    *,
    initial: datetime,
    tz: str = "UTC",
) -> tuple[DailyPnlTracker, FrozenClock, InMemoryEventPublisher, list[Event]]:
    clock = FrozenClock(initial=initial)
    publisher = InMemoryEventPublisher()
    received: list[Event] = []

    async def capture(e: Event) -> None:
        received.append(e)

    publisher.subscribe(Event, capture)

    tracker = DailyPnlTracker(clock=clock, publisher=publisher, tz=tz)
    return tracker, clock, publisher, received


def test_initial_state_zero() -> None:
    tracker, _, _, _ = _make_tracker(initial=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC))
    assert tracker.get() == 0.0


def test_update_persists_value() -> None:
    tracker, _, _, _ = _make_tracker(initial=datetime(2026, 5, 10, tzinfo=UTC))
    tracker.update(-0.025)
    assert tracker.get() == -0.025


def test_current_date_reflects_initial_clock() -> None:
    tracker, _, _, _ = _make_tracker(
        initial=datetime(2026, 5, 10, 23, 30, 0, tzinfo=UTC)
    )
    assert tracker.current_date == date(2026, 5, 10)


@pytest.mark.asyncio
async def test_no_reset_within_same_day() -> None:
    tracker, clock, _, received = _make_tracker(
        initial=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)
    )
    tracker.update(-0.025)

    # 同一天前進 2 小時
    clock.advance(timedelta(hours=2))
    reset = await tracker.maybe_reset()

    assert reset is False
    assert tracker.get() == -0.025
    assert [e for e in received if isinstance(e, DailyPnlReset)] == []


@pytest.mark.asyncio
async def test_reset_on_utc_midnight_boundary() -> None:
    """spec scenario：23:59:59 UTC → 00:00:01 UTC 觸發重置。"""
    tracker, clock, _, received = _make_tracker(
        initial=datetime(2026, 5, 10, 23, 59, 59, tzinfo=UTC)
    )
    tracker.update(-0.025)

    clock.advance(timedelta(seconds=2))  # 跨入 5/11
    reset = await tracker.maybe_reset()

    assert reset is True
    assert tracker.get() == 0.0
    assert tracker.current_date == date(2026, 5, 11)

    daily_resets = [e for e in received if isinstance(e, DailyPnlReset)]
    assert len(daily_resets) == 1


@pytest.mark.asyncio
async def test_only_one_reset_per_day_crossing() -> None:
    """同次跨日多次呼叫 maybe_reset 只觸發一次重置。"""
    tracker, clock, _, received = _make_tracker(
        initial=datetime(2026, 5, 10, 23, 59, 59, tzinfo=UTC)
    )
    clock.advance(timedelta(seconds=2))
    first = await tracker.maybe_reset()
    second = await tracker.maybe_reset()

    assert first is True
    assert second is False
    daily_resets = [e for e in received if isinstance(e, DailyPnlReset)]
    assert len(daily_resets) == 1


@pytest.mark.asyncio
async def test_reset_with_taipei_timezone() -> None:
    """非 UTC 時區：以該時區的午夜為界。"""
    # 初始：UTC 16:00 = 台北 00:00（剛跨入新一天）
    initial = datetime(2026, 5, 10, 16, 0, 0, tzinfo=UTC)
    tracker, clock, _, received = _make_tracker(initial=initial, tz="Asia/Taipei")
    assert tracker.current_date == date(2026, 5, 11)  # 已是台北的 5/11

    tracker.update(-0.03)

    # 前進到 UTC 15:59:59 翌日 = 台北 23:59:59 5/11（仍同日）
    clock.advance(timedelta(hours=23, minutes=59, seconds=59))
    reset_before = await tracker.maybe_reset()
    assert reset_before is False

    # 再前進 2 秒 → 跨入台北 5/12
    clock.advance(timedelta(seconds=2))
    reset_after = await tracker.maybe_reset()
    assert reset_after is True
    assert tracker.get() == 0.0

    daily_resets = [e for e in received if isinstance(e, DailyPnlReset)]
    assert len(daily_resets) == 1


@pytest.mark.asyncio
async def test_multiple_day_crossings_each_emit_event() -> None:
    """連續跨多日：每次跨界都重置 + 發事件。"""
    tracker, clock, _, received = _make_tracker(
        initial=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)
    )
    # 第一次跨日
    clock.advance(timedelta(days=1))
    await tracker.maybe_reset()
    # 第二次跨日
    clock.advance(timedelta(days=1))
    await tracker.maybe_reset()

    daily_resets = [e for e in received if isinstance(e, DailyPnlReset)]
    assert len(daily_resets) == 2
