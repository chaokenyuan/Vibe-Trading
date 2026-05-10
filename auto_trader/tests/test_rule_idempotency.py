"""IdempotencyRule 單元測試。

對應 spec scenario：
- 首次出現的 signal_id 通過
- 5 分鐘內重送被拒絕
- 5 分鐘後重送視為新訊號
- 快取達上限觸發 LRU 淘汰
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from risk.decision import Outcome
from risk.rules.base import RuleContext
from risk.rules.idempotency import IdempotencyRule
from risk.types import OrderIntent, Side
from tests.fakes.frozen_clock import FrozenClock


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


def _ctx(*, signal_id: str, clock: FrozenClock) -> RuleContext:
    intent = OrderIntent(
        strategy_id="A",
        symbol="BTCUSDT",
        side=Side.BUY,
        qty=Decimal("1"),
        price=None,
        signal_id=signal_id,
        bar_time=datetime(2026, 5, 10, tzinfo=UTC),
        received_at=datetime(2026, 5, 10, 0, 0, 1, tzinfo=UTC),
    )
    return RuleContext(
        intent=intent,
        current_size=Decimal("1"),
        current_price=None,
        positions=_FakePositions(),
        market_data=_FakeMarket(),
        config=_FakeConfig(),
        clock=clock,
    )


def test_first_occurrence_passes() -> None:
    """spec scenario：首次出現的 signal_id 通過。"""
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    rule = IdempotencyRule(clock=clock)
    verdict = rule.evaluate(_ctx(signal_id="abc123", clock=clock))
    assert verdict.outcome == Outcome.PASS
    assert rule.cache_size == 1


def test_duplicate_within_ttl_rejected() -> None:
    """spec scenario：5 分鐘內重送被拒絕。"""
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    rule = IdempotencyRule(clock=clock, ttl_seconds=300)

    rule.evaluate(_ctx(signal_id="abc123", clock=clock))
    clock.advance(timedelta(seconds=30))
    verdict = rule.evaluate(_ctx(signal_id="abc123", clock=clock))

    assert verdict.outcome == Outcome.REJECT
    assert "duplicate" in verdict.message.lower()


def test_duplicate_at_ttl_boundary_rejected() -> None:
    """TTL 邊界值（剛好等於）視為仍在 TTL 內。"""
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    rule = IdempotencyRule(clock=clock, ttl_seconds=300)

    rule.evaluate(_ctx(signal_id="abc123", clock=clock))
    clock.advance(timedelta(seconds=300))
    verdict = rule.evaluate(_ctx(signal_id="abc123", clock=clock))
    assert verdict.outcome == Outcome.REJECT


def test_duplicate_after_ttl_passes() -> None:
    """spec scenario：5 分鐘後重送視為新訊號。"""
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    rule = IdempotencyRule(clock=clock, ttl_seconds=300)

    rule.evaluate(_ctx(signal_id="abc123", clock=clock))
    clock.advance(timedelta(seconds=301))
    verdict = rule.evaluate(_ctx(signal_id="abc123", clock=clock))
    assert verdict.outcome == Outcome.PASS


def test_lru_eviction_on_max_entries() -> None:
    """spec scenario：快取達上限觸發 LRU 淘汰。"""
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    rule = IdempotencyRule(clock=clock, ttl_seconds=300, max_entries=3)

    rule.evaluate(_ctx(signal_id="a", clock=clock))
    rule.evaluate(_ctx(signal_id="b", clock=clock))
    rule.evaluate(_ctx(signal_id="c", clock=clock))
    assert rule.cache_size == 3

    # 第 4 個進入觸發淘汰最早的 "a"
    rule.evaluate(_ctx(signal_id="d", clock=clock))
    assert rule.cache_size == 3

    # "a" 已被淘汰：再次出現 → 被視為新（PASS）
    verdict_a = rule.evaluate(_ctx(signal_id="a", clock=clock))
    assert verdict_a.outcome == Outcome.PASS

    # "b"/"c" 仍在快取（但 a 重新進入又踢掉一個 — 此測試只驗證淘汰機制存在）


def test_different_signal_ids_do_not_collide() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    rule = IdempotencyRule(clock=clock)

    v1 = rule.evaluate(_ctx(signal_id="sig_001", clock=clock))
    v2 = rule.evaluate(_ctx(signal_id="sig_002", clock=clock))
    assert v1.outcome == Outcome.PASS
    assert v2.outcome == Outcome.PASS
    assert rule.cache_size == 2


def test_custom_ttl_respected() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    rule = IdempotencyRule(clock=clock, ttl_seconds=10)

    rule.evaluate(_ctx(signal_id="x", clock=clock))
    clock.advance(timedelta(seconds=11))
    assert rule.evaluate(_ctx(signal_id="x", clock=clock)).outcome == Outcome.PASS


def test_ttl_property_exposes_timedelta() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    rule = IdempotencyRule(clock=clock, ttl_seconds=300)
    assert rule.ttl == timedelta(seconds=300)
