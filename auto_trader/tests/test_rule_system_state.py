"""SystemStateRule 單元測試。

對應 spec scenario：
- NORMAL/WARNING 通過
- THROTTLED 縮量 50%
- HALTED/KILL_SWITCH/MAINTENANCE 拒絕
- 訂閱 StateChanged 事件即時更新
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.decision import Outcome
from risk.events import StateChanged
from risk.rules.base import RuleContext
from risk.rules.system_state import SystemStateRule
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


def _ctx(qty: Decimal = Decimal("10")) -> RuleContext:
    intent = OrderIntent(
        strategy_id="A",
        symbol="BTCUSDT",
        side=Side.BUY,
        qty=qty,
        price=None,
        signal_id="sig",
        bar_time=datetime(2026, 5, 10, tzinfo=UTC),
        received_at=datetime(2026, 5, 10, 0, 0, 1, tzinfo=UTC),
    )
    return RuleContext(
        intent=intent,
        current_size=qty,
        current_price=None,
        positions=_FakePositions(),
        market_data=_FakeMarket(),
        config=_FakeConfig(),
        clock=FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC)),
    )


def test_normal_state_passes() -> None:
    rule = SystemStateRule(initial_state="NORMAL", publisher=InMemoryEventPublisher())
    verdict = rule.evaluate(_ctx())
    assert verdict.outcome == Outcome.PASS
    assert verdict.before_value == Decimal("10")
    assert verdict.after_value == Decimal("10")


def test_warning_state_passes() -> None:
    rule = SystemStateRule(initial_state="WARNING", publisher=InMemoryEventPublisher())
    verdict = rule.evaluate(_ctx())
    assert verdict.outcome == Outcome.PASS


def test_throttled_state_clamps_50_pct() -> None:
    """spec scenario：THROTTLED 狀態縮量 50%。"""
    rule = SystemStateRule(initial_state="THROTTLED", publisher=InMemoryEventPublisher())
    verdict = rule.evaluate(_ctx(qty=Decimal("10")))
    assert verdict.outcome == Outcome.CLAMP
    assert verdict.before_value == Decimal("10")
    assert verdict.after_value == Decimal("5")


def test_halted_state_rejects() -> None:
    """spec scenario：HALTED 狀態拒絕。"""
    rule = SystemStateRule(initial_state="HALTED", publisher=InMemoryEventPublisher())
    verdict = rule.evaluate(_ctx())
    assert verdict.outcome == Outcome.REJECT
    assert "HALTED" in verdict.message


def test_kill_switch_state_rejects() -> None:
    rule = SystemStateRule(initial_state="KILL_SWITCH", publisher=InMemoryEventPublisher())
    verdict = rule.evaluate(_ctx())
    assert verdict.outcome == Outcome.REJECT
    assert "KILL_SWITCH" in verdict.message


def test_maintenance_state_rejects() -> None:
    """spec scenario：維護期間拒絕 OrderIntent。"""
    rule = SystemStateRule(initial_state="MAINTENANCE", publisher=InMemoryEventPublisher())
    verdict = rule.evaluate(_ctx())
    assert verdict.outcome == Outcome.REJECT
    assert "MAINTENANCE" in verdict.message


@pytest.mark.asyncio
async def test_state_changed_event_updates_cache() -> None:
    """訂閱 StateChanged 事件即時更新內部狀態快取。"""
    pub = InMemoryEventPublisher()
    rule = SystemStateRule(initial_state="NORMAL", publisher=pub)

    assert rule.evaluate(_ctx()).outcome == Outcome.PASS

    await pub.publish(
        StateChanged(
            at=datetime(2026, 5, 10, tzinfo=UTC),
            from_state="NORMAL",
            to_state="THROTTLED",
            reason="test",
        )
    )
    assert rule.current_state == "THROTTLED"
    assert rule.evaluate(_ctx(qty=Decimal("10"))).outcome == Outcome.CLAMP


def test_custom_throttled_scaler() -> None:
    rule = SystemStateRule(
        initial_state="THROTTLED",
        publisher=InMemoryEventPublisher(),
        throttled_size_scaler=Decimal("0.3"),
    )
    verdict = rule.evaluate(_ctx(qty=Decimal("10")))
    assert verdict.after_value == Decimal("3.0")
