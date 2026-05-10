"""SignalDedupe 測試。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from signals.dedupe import SignalDedupe
from tests.fakes.frozen_clock import FrozenClock


def _make_dedupe(ttl: int = 300, max_entries: int = 100_000) -> SignalDedupe:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    return SignalDedupe(clock=clock, ttl_seconds=ttl, max_entries=max_entries)


def test_first_signal_id_not_duplicate() -> None:
    dedupe = _make_dedupe()
    assert dedupe.is_duplicate("abc") is False
    assert dedupe.size == 1


def test_repeat_within_ttl_is_duplicate() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    dedupe = SignalDedupe(clock=clock, ttl_seconds=300)
    dedupe.is_duplicate("abc")
    clock.advance(timedelta(seconds=30))
    assert dedupe.is_duplicate("abc") is True


def test_after_ttl_not_duplicate_and_overwrite() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    dedupe = SignalDedupe(clock=clock, ttl_seconds=300)
    dedupe.is_duplicate("abc")
    clock.advance(timedelta(seconds=301))
    assert dedupe.is_duplicate("abc") is False


def test_lru_eviction_when_over_max_entries() -> None:
    dedupe = _make_dedupe(max_entries=3)
    dedupe.is_duplicate("a")
    dedupe.is_duplicate("b")
    dedupe.is_duplicate("c")
    assert dedupe.size == 3
    dedupe.is_duplicate("d")  # 觸發淘汰
    assert dedupe.size == 3
    # "a" 應已被淘汰
    assert dedupe.is_duplicate("a") is False


def test_distinct_ids_no_collision() -> None:
    dedupe = _make_dedupe()
    assert dedupe.is_duplicate("x") is False
    assert dedupe.is_duplicate("y") is False
    assert dedupe.is_duplicate("z") is False
    assert dedupe.size == 3
