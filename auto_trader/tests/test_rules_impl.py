"""9 條已實作規則測試（取代既有 _stubs.py 對應的 NotImplementedError 測試）。"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.decision import Outcome
from risk.reservation.ledger import ReservationLedger
from risk.reservation.reserver import CapitalReserver
from risk.rules.base import RuleContext
from risk.rules.capital_reservation import CapitalReservationRule
from risk.rules.freshness import SignalFreshnessRule
from risk.rules.per_order_size_cap import PerOrderSizeCap
from risk.rules.price_sanity_check import PriceSanityCheck
from risk.rules.strategy_budget_cap import StrategyBudgetCap
from risk.rules.strategy_paused import StrategyPausedRule
from risk.rules.symbol_concentration_cap import SymbolConcentrationCap
from risk.rules.throttle_scaler import ThrottleScaler
from risk.rules.whitelist import SymbolWhitelistRule
from risk.types import OrderIntent, Side
from tests.fakes.frozen_clock import FrozenClock


class _FakeMarket:
    def __init__(self, last: Decimal = Decimal("65000")) -> None:
        self._last = last

    def get_last_price(self, symbol: str) -> Decimal:
        return self._last


class _FakePositions:
    def get_position(self, sid: str, sym: str) -> Any:
        return None

    def list_positions(self) -> list[Any]:
        return []


class _FakeConfig:
    def get(self, k: str) -> Any:
        return None


class _ActiveStateReader:
    def get_state(self, sid: str) -> str | None:
        return "ACTIVE"


class _PausedStateReader:
    def get_state(self, sid: str) -> str | None:
        return "PAUSED"


class _NoneStateReader:
    def get_state(self, sid: str) -> str | None:
        return None


def _ctx(
    *,
    qty: Decimal = Decimal("1"),
    price: Decimal | None = Decimal("65000"),
    bar_time: datetime | None = None,
    symbol: str = "BTCUSDT",
    clock: FrozenClock | None = None,
    market: _FakeMarket | None = None,
) -> RuleContext:
    if clock is None:
        clock = FrozenClock(initial=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC))
    if market is None:
        market = _FakeMarket()
    intent = OrderIntent(
        strategy_id="A",
        symbol=symbol,
        side=Side.BUY,
        qty=qty,
        price=price,
        signal_id="sig",
        bar_time=bar_time or datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC),
        received_at=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC),
    )
    return RuleContext(
        intent=intent,
        current_size=qty,
        current_price=price,
        positions=_FakePositions(),
        market_data=market,
        config=_FakeConfig(),
        clock=clock,
    )


# ===== SignalFreshnessRule =====


def test_freshness_within_threshold_passes() -> None:
    rule = SignalFreshnessRule(max_age_seconds=30)
    clock = FrozenClock(initial=datetime(2026, 5, 10, 12, 0, 10, tzinfo=UTC))
    ctx = _ctx(
        bar_time=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC), clock=clock
    )
    assert rule.evaluate(ctx).outcome == Outcome.PASS


def test_freshness_exceeds_threshold_rejected() -> None:
    rule = SignalFreshnessRule(max_age_seconds=30)
    clock = FrozenClock(initial=datetime(2026, 5, 10, 12, 1, 0, tzinfo=UTC))
    ctx = _ctx(
        bar_time=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC), clock=clock
    )
    verdict = rule.evaluate(ctx)
    assert verdict.outcome == Outcome.REJECT
    assert "60" in verdict.message or "60s" in verdict.message


# ===== SymbolWhitelistRule =====


def test_whitelist_empty_accepts_all() -> None:
    rule = SymbolWhitelistRule()
    assert rule.evaluate(_ctx(symbol="BTCUSDT")).outcome == Outcome.PASS
    assert rule.evaluate(_ctx(symbol="DOGE_USDT")).outcome == Outcome.PASS


def test_whitelist_in_list_passes() -> None:
    rule = SymbolWhitelistRule(symbols=["BTCUSDT", "ETHUSDT"])
    assert rule.evaluate(_ctx(symbol="BTCUSDT")).outcome == Outcome.PASS


def test_whitelist_not_in_list_rejected() -> None:
    rule = SymbolWhitelistRule(symbols=["BTCUSDT"])
    verdict = rule.evaluate(_ctx(symbol="SOLUSDT"))
    assert verdict.outcome == Outcome.REJECT


# ===== StrategyPausedRule =====


def test_strategy_paused_active_passes() -> None:
    rule = StrategyPausedRule(state_reader=_ActiveStateReader())
    assert rule.evaluate(_ctx()).outcome == Outcome.PASS


def test_strategy_paused_paused_rejected() -> None:
    rule = StrategyPausedRule(state_reader=_PausedStateReader())
    assert rule.evaluate(_ctx()).outcome == Outcome.REJECT


def test_strategy_paused_unknown_rejected() -> None:
    rule = StrategyPausedRule(state_reader=_NoneStateReader())
    assert rule.evaluate(_ctx()).outcome == Outcome.REJECT


# ===== PerOrderSizeCap =====


class _FakeEquity:
    def __init__(self, equity: Decimal) -> None:
        self._equity = equity

    @property
    def total_equity(self) -> Decimal:
        return self._equity


def test_per_order_cap_clamps_when_size_exceeds() -> None:
    rule = PerOrderSizeCap(
        equity_reader=_FakeEquity(Decimal("10000")),
        max_pct_of_equity=Decimal("0.05"),
    )
    # cap notional = 500，price=1 → qty_cap=500
    ctx = _ctx(qty=Decimal("1000"), price=Decimal("1"))
    verdict = rule.evaluate(ctx)
    assert verdict.outcome == Outcome.CLAMP
    assert verdict.after_value == Decimal("500")


def test_per_order_cap_passes_within_limit() -> None:
    rule = PerOrderSizeCap(
        equity_reader=_FakeEquity(Decimal("10000")),
        max_pct_of_equity=Decimal("0.05"),
    )
    ctx = _ctx(qty=Decimal("100"), price=Decimal("1"))
    assert rule.evaluate(ctx).outcome == Outcome.PASS


def test_per_order_cap_uses_market_when_price_none() -> None:
    rule = PerOrderSizeCap(
        equity_reader=_FakeEquity(Decimal("10000")),
        max_pct_of_equity=Decimal("0.05"),
    )
    ctx = _ctx(qty=Decimal("1000"), price=None, market=_FakeMarket(Decimal("1")))
    verdict = rule.evaluate(ctx)
    assert verdict.outcome == Outcome.CLAMP
    assert verdict.after_value == Decimal("500")


# ===== StrategyBudgetCap =====


def _ledger(
    *,
    equity: Decimal = Decimal("100000"),
    a_budget: Decimal = Decimal("5000"),
    btc_cap: Decimal = Decimal("4000"),
) -> ReservationLedger:
    return ReservationLedger(
        total_equity=equity,
        strategy_budgets={"A": a_budget},
        symbol_caps={"BTCUSDT": btc_cap},
    )


def test_strategy_budget_cap_clamps() -> None:
    ledger = _ledger(a_budget=Decimal("500"))
    rule = StrategyBudgetCap(ledger_reader=ledger)
    # available=500, price=10 → qty_cap=50
    ctx = _ctx(qty=Decimal("100"), price=Decimal("10"))
    verdict = rule.evaluate(ctx)
    assert verdict.outcome == Outcome.CLAMP
    assert verdict.after_value == Decimal("50")


def test_strategy_budget_cap_passes_within_limit() -> None:
    rule = StrategyBudgetCap(ledger_reader=_ledger())  # A budget=5000
    ctx = _ctx(qty=Decimal("1"), price=Decimal("65000"))  # notional=65000 > 5000？
    # 不對，A budget 5000，price=65000，cap=5000/65000=0.0769
    verdict = rule.evaluate(ctx)
    assert verdict.outcome == Outcome.CLAMP
    # 換個小 size 場景
    rule2 = StrategyBudgetCap(ledger_reader=_ledger())
    ctx2 = _ctx(qty=Decimal("0.05"), price=Decimal("65000"))  # 已 < 5000/65000
    assert rule2.evaluate(ctx2).outcome == Outcome.PASS


# ===== SymbolConcentrationCap =====


def test_symbol_concentration_clamps() -> None:
    ledger = _ledger(btc_cap=Decimal("300"))
    rule = SymbolConcentrationCap(ledger_reader=ledger)
    ctx = _ctx(qty=Decimal("100"), price=Decimal("10"))
    verdict = rule.evaluate(ctx)
    assert verdict.outcome == Outcome.CLAMP
    assert verdict.after_value == Decimal("30")


def test_symbol_concentration_unbounded_for_unknown_symbol() -> None:
    ledger = _ledger()
    rule = SymbolConcentrationCap(ledger_reader=ledger)
    ctx = _ctx(symbol="UNKNOWN_SYMBOL", qty=Decimal("1000000"), price=Decimal("1"))
    assert rule.evaluate(ctx).outcome == Outcome.PASS


# ===== ThrottleScaler =====


def test_throttle_scaler_default_passes() -> None:
    rule = ThrottleScaler()
    assert rule.evaluate(_ctx()).outcome == Outcome.PASS


def test_throttle_scaler_clamps_when_below_one() -> None:
    rule = ThrottleScaler(scaler=Decimal("0.5"))
    ctx = _ctx(qty=Decimal("10"))
    verdict = rule.evaluate(ctx)
    assert verdict.outcome == Outcome.CLAMP
    assert verdict.after_value == Decimal("5.0")


# ===== PriceSanityCheck =====


def test_price_sanity_market_order_passes() -> None:
    rule = PriceSanityCheck()
    ctx = _ctx(price=None)
    assert rule.evaluate(ctx).outcome == Outcome.PASS


def test_price_sanity_within_deviation_passes() -> None:
    rule = PriceSanityCheck(max_deviation_pct=Decimal("0.05"))
    ctx = _ctx(price=Decimal("65000"), market=_FakeMarket(Decimal("65500")))
    assert rule.evaluate(ctx).outcome == Outcome.PASS


def test_price_sanity_over_deviation_rejected() -> None:
    rule = PriceSanityCheck(max_deviation_pct=Decimal("0.05"))
    ctx = _ctx(price=Decimal("70000"), market=_FakeMarket(Decimal("65000")))
    assert rule.evaluate(ctx).outcome == Outcome.REJECT


def test_price_sanity_zero_last_passes() -> None:
    rule = PriceSanityCheck()
    ctx = _ctx(price=Decimal("65000"), market=_FakeMarket(Decimal("0")))
    assert rule.evaluate(ctx).outcome == Outcome.PASS


# ===== CapitalReservationRule =====


@pytest.mark.asyncio
async def test_capital_reservation_success_metadata_has_reservation_id() -> None:
    publisher = InMemoryEventPublisher()
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    ledger = _ledger(equity=Decimal("100000"), a_budget=Decimal("100000"), btc_cap=Decimal("100000"))
    reserver = CapitalReserver(ledger=ledger, clock=clock, publisher=publisher)
    await reserver.start()

    try:
        rule = CapitalReservationRule(reserver=reserver)
        ctx = _ctx(qty=Decimal("1"), price=Decimal("65000"), clock=clock)
        verdict = await rule.evaluate_async(ctx)
    finally:
        await reserver.stop()

    assert verdict.outcome == Outcome.PASS
    assert "reservation_id" in verdict.metadata
    # reservation_id 為 UUID 字串
    rid = verdict.metadata["reservation_id"]
    assert len(rid) == 36  # UUID 字串長度


@pytest.mark.asyncio
async def test_capital_reservation_failure_rejects() -> None:
    publisher = InMemoryEventPublisher()
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    ledger = _ledger(equity=Decimal("100"), a_budget=Decimal("100"), btc_cap=Decimal("100"))
    reserver = CapitalReserver(ledger=ledger, clock=clock, publisher=publisher)
    await reserver.start()

    try:
        rule = CapitalReservationRule(reserver=reserver)
        # qty=1 price=65000 → notional=65000 > available 100
        ctx = _ctx(qty=Decimal("1"), price=Decimal("65000"), clock=clock)
        verdict = await rule.evaluate_async(ctx)
    finally:
        await reserver.stop()

    assert verdict.outcome == Outcome.REJECT


def test_capital_reservation_sync_evaluate_raises() -> None:
    """同步 evaluate 拋例外（rule 必須以 async 呼叫）。"""
    publisher = InMemoryEventPublisher()
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    reserver = CapitalReserver(ledger=_ledger(), clock=clock, publisher=publisher)
    rule = CapitalReservationRule(reserver=reserver)
    with pytest.raises(RuntimeError, match="evaluate_async"):
        rule.evaluate(_ctx(clock=clock))
