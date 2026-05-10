"""FrozenClock 單元測試：時間前進、tz 處理、monotonic 與 wall-clock 同步。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from tests.fakes.frozen_clock import FrozenClock


def test_initial_now_returns_initial() -> None:
    initial = datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)
    clock = FrozenClock(initial=initial)
    assert clock.now() == initial


def test_initial_monotonic_is_zero() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    assert clock.monotonic() == 0.0


def test_advance_moves_now_forward() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC))
    clock.advance(timedelta(minutes=6))
    assert clock.now() == datetime(2026, 5, 10, 12, 6, 0, tzinfo=UTC)


def test_advance_moves_monotonic_in_sync() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    clock.advance(timedelta(seconds=30))
    assert clock.monotonic() == 30.0


def test_advance_zero_is_noop() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    before_now = clock.now()
    before_monotonic = clock.monotonic()
    clock.advance(timedelta(0))
    assert clock.now() == before_now
    assert clock.monotonic() == before_monotonic


def test_advance_negative_raises() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    with pytest.raises(ValueError, match="負時間"):
        clock.advance(timedelta(seconds=-1))


def test_set_jumps_to_target() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    target = datetime(2026, 5, 11, 8, 0, 0, tzinfo=UTC)
    clock.set(target)
    assert clock.now() == target


def test_set_does_not_change_monotonic() -> None:
    """set 是 wall-clock 跳躍，不應改 monotonic（保持 timer 語意）。"""
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    clock.advance(timedelta(seconds=10))
    monotonic_before = clock.monotonic()
    clock.set(datetime(2030, 1, 1, tzinfo=UTC))
    assert clock.monotonic() == monotonic_before


def test_initial_without_tzinfo_raises() -> None:
    with pytest.raises(ValueError, match="tzinfo"):
        FrozenClock(initial=datetime(2026, 5, 10, 12, 0, 0))


def test_set_without_tzinfo_raises() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    with pytest.raises(ValueError, match="tzinfo"):
        clock.set(datetime(2026, 5, 11))


def test_supports_non_utc_tz() -> None:
    """tz 處理：不同時區的時間都能正確保存。"""
    tz_taipei = timezone(timedelta(hours=8))
    clock = FrozenClock(initial=datetime(2026, 5, 10, 20, 0, 0, tzinfo=tz_taipei))
    assert clock.now().tzinfo == tz_taipei
    assert clock.now() == datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)


def test_advance_across_day_boundary() -> None:
    """跨日（UTC）：FSM 每日 P&L 重置依此判定。"""
    clock = FrozenClock(initial=datetime(2026, 5, 10, 23, 59, 59, tzinfo=UTC))
    clock.advance(timedelta(seconds=2))
    assert clock.now() == datetime(2026, 5, 11, 0, 0, 1, tzinfo=UTC)


def test_satisfies_clock_protocol_via_runtime_checkable() -> None:
    """結構驗證：FrozenClock 滿足 risk.ports.Clock Protocol。"""
    from risk.ports import Clock

    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    assert isinstance(clock, Clock)
