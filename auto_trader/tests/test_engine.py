"""RuleEngine 單元測試。

對應 spec scenarios：
- Reject 規則短路（後續規則不評估）
- Clamp 規則累積收斂（10 → 8 → 6 → 5）
- Clamp 違反單調遞減在 debug 模式拋例外
- DecisionEmitted 事件每筆觸發
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.decision import Outcome, RuleVerdict, Verdict
from risk.engine import RuleEngine
from risk.events import DecisionEmitted, Event
from risk.rules.base import RuleContext
from risk.types import OrderIntent, Side
from tests.fakes.frozen_clock import FrozenClock

# ===== 測試替身 =====


class _FakePositionReader:
    def get_position(self, strategy_id: str, symbol: str) -> Any:
        return None

    def list_positions(self) -> list[Any]:
        return []


class _FakeMarketData:
    def get_last_price(self, symbol: str) -> Decimal:
        return Decimal("65000")


class _FakeConfig:
    def get(self, key: str) -> Any:
        return None


class _PassRule:
    def __init__(self, name: str = "Pass") -> None:
        self.name = name
        self.calls = 0

    def evaluate(self, ctx: RuleContext) -> RuleVerdict:
        self.calls += 1
        return RuleVerdict(
            rule_name=self.name,
            outcome=Outcome.PASS,
            before_value=ctx.current_size,
            after_value=ctx.current_size,
            message="pass",
        )


class _RejectRule:
    def __init__(self, name: str = "Reject") -> None:
        self.name = name
        self.calls = 0

    def evaluate(self, ctx: RuleContext) -> RuleVerdict:
        self.calls += 1
        return RuleVerdict(
            rule_name=self.name,
            outcome=Outcome.REJECT,
            before_value=ctx.current_size,
            after_value=None,
            message="rejected",
        )


class _ClampRule:
    def __init__(self, max_size: Decimal, name: str = "Clamp") -> None:
        self.name = name
        self._max = max_size
        self.calls = 0

    def evaluate(self, ctx: RuleContext) -> RuleVerdict:
        self.calls += 1
        after = min(ctx.current_size, self._max)
        return RuleVerdict(
            rule_name=self.name,
            outcome=Outcome.CLAMP if after < ctx.current_size else Outcome.PASS,
            before_value=ctx.current_size,
            after_value=after,
            message=f"max={self._max}",
        )


class _BadClampRule:
    """違反單調遞減的 clamp 規則（after > before）。"""

    name = "BadClamp"

    def evaluate(self, ctx: RuleContext) -> RuleVerdict:
        return RuleVerdict(
            rule_name=self.name,
            outcome=Outcome.CLAMP,
            before_value=ctx.current_size,
            after_value=ctx.current_size + Decimal("1"),  # 增大！
            message="bad",
        )


def _make_intent(qty: Decimal = Decimal("10")) -> OrderIntent:
    return OrderIntent(
        strategy_id="A",
        symbol="BTCUSDT",
        side=Side.BUY,
        qty=qty,
        price=Decimal("65000"),
        signal_id="sig_1",
        bar_time=datetime(2026, 5, 10, tzinfo=UTC),
        received_at=datetime(2026, 5, 10, 0, 0, 1, tzinfo=UTC),
    )


def _make_engine(rules: list[Any], debug_mode: bool = False) -> tuple[RuleEngine, list[Event]]:
    publisher = InMemoryEventPublisher()
    received: list[Event] = []

    async def capture(e: Event) -> None:
        received.append(e)

    publisher.subscribe(Event, capture)

    engine = RuleEngine(
        rules=rules,
        publisher=publisher,
        clock=FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC)),
        positions=_FakePositionReader(),
        market_data=_FakeMarketData(),
        config=_FakeConfig(),
        debug_mode=debug_mode,
    )
    return engine, received


# ===== 短路測試 =====


@pytest.mark.asyncio
async def test_reject_rule_short_circuits_subsequent() -> None:
    """spec scenario：Reject 規則短路，後續規則不評估。"""
    a = _RejectRule(name="A")
    b = _PassRule(name="B")
    c = _PassRule(name="C")
    engine, _ = _make_engine([a, b, c])

    decision = await engine.evaluate(_make_intent())

    assert decision.verdict == Verdict.REJECT
    assert a.calls == 1
    assert b.calls == 0
    assert c.calls == 0
    # reasons 僅包含 A 的 verdict
    assert len(decision.reasons) == 1
    assert decision.reasons[0].rule_name == "A"


@pytest.mark.asyncio
async def test_all_pass_results_in_approve() -> None:
    a = _PassRule(name="A")
    b = _PassRule(name="B")
    engine, _ = _make_engine([a, b])

    decision = await engine.evaluate(_make_intent())

    assert decision.verdict == Verdict.APPROVE
    assert decision.final_size == Decimal("10")
    assert len(decision.reasons) == 2


# ===== Clamp 累積測試 =====


@pytest.mark.asyncio
async def test_clamp_rules_accumulate_size_reduction() -> None:
    """spec scenario：Clamp 累積收斂（10 → 8 → 6 → 5）。"""
    rules = [
        _ClampRule(Decimal("8"), name="PerOrderSizeCap"),
        _ClampRule(Decimal("6"), name="StrategyBudgetCap"),
        _ClampRule(Decimal("5"), name="SymbolConcentrationCap"),
    ]
    engine, _ = _make_engine(rules)

    decision = await engine.evaluate(_make_intent(qty=Decimal("10")))

    assert decision.verdict == Verdict.APPROVE
    assert decision.final_size == Decimal("5")
    # 三條都評估了
    assert len(decision.reasons) == 3
    # before/after 鏈正確
    assert decision.reasons[0].before_value == Decimal("10")
    assert decision.reasons[0].after_value == Decimal("8")
    assert decision.reasons[1].before_value == Decimal("8")
    assert decision.reasons[1].after_value == Decimal("6")
    assert decision.reasons[2].before_value == Decimal("6")
    assert decision.reasons[2].after_value == Decimal("5")


@pytest.mark.asyncio
async def test_clamp_pass_when_already_below_limit() -> None:
    """current_size < clamp limit 時規則回 PASS（不修改）。"""
    engine, _ = _make_engine([_ClampRule(Decimal("100"), name="High")])
    decision = await engine.evaluate(_make_intent(qty=Decimal("10")))
    assert decision.verdict == Verdict.APPROVE
    assert decision.final_size == Decimal("10")
    assert decision.reasons[0].outcome == Outcome.PASS


# ===== 單調遞減 invariant =====


@pytest.mark.asyncio
async def test_bad_clamp_in_debug_raises() -> None:
    """spec scenario：clamp 違反單調遞減在 debug 模式拋例外。"""
    engine, _ = _make_engine([_BadClampRule()], debug_mode=True)
    with pytest.raises(ValueError, match="單調遞減"):
        await engine.evaluate(_make_intent())


@pytest.mark.asyncio
async def test_bad_clamp_in_production_ignored(caplog: pytest.LogCaptureFixture) -> None:
    """Production 模式下 clamp 違反單調遞減 → 記錄錯誤並忽略修正值。"""
    import logging

    engine, _ = _make_engine([_BadClampRule()], debug_mode=False)
    with caplog.at_level(logging.ERROR):
        decision = await engine.evaluate(_make_intent())

    assert decision.verdict == Verdict.APPROVE
    # final_size 維持原值（忽略 bad clamp）
    assert decision.final_size == Decimal("10")
    assert any("單調遞減" in r.message for r in caplog.records)


# ===== DecisionEmitted 事件 =====


@pytest.mark.asyncio
async def test_decision_emitted_event_per_evaluation() -> None:
    """spec scenario：每筆 Decision 觸發一個事件。"""
    engine, received = _make_engine([_PassRule()])

    await engine.evaluate(_make_intent())
    await engine.evaluate(_make_intent())

    decision_events = [e for e in received if isinstance(e, DecisionEmitted)]
    assert len(decision_events) == 2


@pytest.mark.asyncio
async def test_decision_event_carries_full_decision() -> None:
    engine, received = _make_engine([_RejectRule()])
    await engine.evaluate(_make_intent())

    [event] = [e for e in received if isinstance(e, DecisionEmitted)]
    assert event.decision.verdict == Verdict.REJECT
    assert event.decision.final_size == Decimal("0")
    assert len(event.decision.reasons) == 1


# ===== 空規則清單 =====


@pytest.mark.asyncio
async def test_empty_rules_approves_with_original_size() -> None:
    engine, _ = _make_engine([])
    decision = await engine.evaluate(_make_intent(qty=Decimal("7")))
    assert decision.verdict == Verdict.APPROVE
    assert decision.final_size == Decimal("7")
    assert decision.reasons == []
