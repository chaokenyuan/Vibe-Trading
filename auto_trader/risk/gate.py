"""RiskGate：對外唯一進入點。組合 StateMachine + RuleEngine + CapitalReserver。

對應 spec：「啟動時暖機 30 秒不接受 OrderIntent」、「配置以 YAML 表達且啟動時驗證」。

部署用法：
    gate = RiskGate.from_config(
        config_path="config/risk.yaml",
        total_equity=Decimal("10000"),
        strategy_budgets={"A": Decimal("5000")},
        symbol_caps={"BTCUSDT": Decimal("4000")},
        positions=...,
        market_data=...,
        config_reader=...,
    )
    await gate.start(metrics_provider)
    decision = await gate.evaluate(intent)
    await gate.shutdown()
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.adapters.system_clock import SystemClock
from risk.config import RiskConfig
from risk.decision import Decision, Outcome, RuleVerdict, Verdict
from risk.engine import RuleEngine
from risk.events import ConfigLoaded
from risk.ports import (
    Clock,
    ConfigReader,
    MarketDataReader,
    PositionReader,
    StateStore,
    StrategyStateReader,
)
from risk.reservation.ledger import ReservationLedger
from risk.reservation.reserver import CapitalReserver
from risk.rules.base import RiskRule
from risk.rules.capital_reservation import CapitalReservationRule
from risk.rules.freshness import SignalFreshnessRule
from risk.rules.idempotency import IdempotencyRule
from risk.rules.per_order_size_cap import PerOrderSizeCap
from risk.rules.price_sanity_check import PriceSanityCheck
from risk.rules.strategy_budget_cap import StrategyBudgetCap
from risk.rules.strategy_paused import StrategyPausedRule
from risk.rules.symbol_concentration_cap import SymbolConcentrationCap
from risk.rules.system_state import SystemStateRule
from risk.rules.throttle_scaler import ThrottleScaler
from risk.rules.whitelist import SymbolWhitelistRule
from risk.state.machine import MetricsProvider, StateMachine
from risk.state.persistence import InMemoryStateStore
from risk.state.states import SystemState
from risk.types import OrderIntent

RuleBuilder = Callable[[], RiskRule]


class RiskGate:
    """風控閘對外門面（capability 唯一進入點）。"""

    def __init__(
        self,
        *,
        config: RiskConfig,
        clock: Clock,
        store: StateStore,
        publisher: InMemoryEventPublisher,
        positions: PositionReader,
        market_data: MarketDataReader,
        config_reader: ConfigReader,
        ledger: ReservationLedger,
        strategy_state_reader: StrategyStateReader | None = None,
    ) -> None:
        self._config = config
        self._clock = clock
        self._publisher = publisher
        self._ledger = ledger
        self._strategy_state_reader = strategy_state_reader or _AlwaysActiveStateReader()

        # 建構 StateMachine（讀回上次狀態 + 暖機初始）
        self._state_machine = StateMachine(
            clock=clock,
            store=store,
            publisher=publisher,
            thresholds=config.fsm.thresholds,
            cooling_seconds=config.fsm.thresholds.kill_switch_cooling_seconds,
            tick_interval_seconds=config.fsm.tick_interval_seconds,
        )

        # 建構 CapitalReserver actor
        self._reserver = CapitalReserver(
            ledger=ledger,
            clock=clock,
            publisher=publisher,
        )

        # 依 config.rules.enabled 順序建構規則清單
        rules = self._build_rules(
            config=config,
            publisher=publisher,
            clock=clock,
            initial_state=self._state_machine.state.value,
        )
        self._engine = RuleEngine(
            rules=rules,
            publisher=publisher,
            clock=clock,
            positions=positions,
            market_data=market_data,
            config=config_reader,
        )

        # 暖機期狀態
        self._warming_up_until: float | None = None
        self._started = False
        self._stopped = False

    @classmethod
    def from_config(
        cls,
        *,
        config_path: str | Path,
        total_equity: Decimal,
        strategy_budgets: dict[str, Decimal],
        symbol_caps: dict[str, Decimal],
        positions: PositionReader,
        market_data: MarketDataReader,
        config_reader: ConfigReader,
    ) -> RiskGate:
        """從 YAML 配置建構 RiskGate。

        非配置項（total_equity、strategy_budgets、symbol_caps、ports）
        須由呼叫端提供，因為這些屬於 runtime 而非靜態配置。
        """
        config = RiskConfig.from_yaml(config_path)
        clock = SystemClock()
        store = InMemoryStateStore()
        publisher = InMemoryEventPublisher()
        ledger = ReservationLedger(
            total_equity=total_equity,
            strategy_budgets=strategy_budgets,
            symbol_caps=symbol_caps,
        )
        return cls(
            config=config,
            clock=clock,
            store=store,
            publisher=publisher,
            positions=positions,
            market_data=market_data,
            config_reader=config_reader,
            ledger=ledger,
        )

    async def start(self, metrics_provider: MetricsProvider | None = None) -> None:
        """啟動所有後台任務並進入暖機期。

        metrics_provider 為 None 時，FSM 不啟動自動 tick 循環，
        但 StateMachine 仍可被呼叫者手動 tick。
        """
        if self._started:
            raise RuntimeError("RiskGate already started")

        await self._reserver.start()

        if metrics_provider is not None:
            await self._state_machine.start(metrics_provider)

        # 暖機期截止時間（monotonic）
        self._warming_up_until = (
            self._clock.monotonic() + self._config.warming_up.duration_seconds
        )

        # 發布 ConfigLoaded 事件含 params_hash
        await self._publisher.publish(
            ConfigLoaded(
                at=self._clock.now(),
                params_hash=self._config.params_hash(),
            )
        )
        self._started = True

    async def shutdown(self) -> None:
        """優雅停機：停 reserver、stop FSM、標記 stopped。"""
        await self._state_machine.stop()
        await self._reserver.stop()
        self._stopped = True

    async def evaluate(self, intent: OrderIntent) -> Decision:
        """對外主介面：對單筆 OrderIntent 執行完整風控評估。

        - 系統已停機 → RuntimeError
        - 暖機期內 → Decision(verdict=REJECT, reason=system_warming_up)
        - 否則 → 走 RuleEngine
        """
        if self._stopped:
            raise RuntimeError("RiskGate is stopped")

        if self._is_warming_up():
            return self._reject_warming_up(intent)

        return await self._engine.evaluate(intent)

    def _is_warming_up(self) -> bool:
        if self._warming_up_until is None:
            return False
        return self._clock.monotonic() < self._warming_up_until

    def _reject_warming_up(self, intent: OrderIntent) -> Decision:
        verdict = RuleVerdict(
            rule_name="WarmingUp",
            outcome=Outcome.REJECT,
            before_value=intent.qty,
            after_value=None,
            message="system_warming_up",
            metadata={"warming_up_remaining_seconds": self._warming_up_remaining()},
        )
        return Decision(
            verdict=Verdict.REJECT,
            final_size=Decimal(0),
            final_price=None,
            reasons=[verdict],
            reservation_id=None,
            evaluated_at=self._clock.now(),
        )

    def _warming_up_remaining(self) -> float:
        if self._warming_up_until is None:
            return 0.0
        return max(self._warming_up_until - self._clock.monotonic(), 0.0)

    def _build_rules(
        self,
        *,
        config: RiskConfig,
        publisher: InMemoryEventPublisher,
        clock: Clock,
        initial_state: str,
    ) -> list[RiskRule]:
        params = config.rules.params

        def _build_system_state() -> RiskRule:
            sub = params.for_rule("SystemStateRule")
            scaler = Decimal(str(sub.get("throttled_size_scaler", "0.5")))
            return SystemStateRule(
                initial_state=initial_state,
                publisher=publisher,
                throttled_size_scaler=scaler,
            )

        def _build_idempotency() -> RiskRule:
            sub = params.for_rule("IdempotencyRule")
            return IdempotencyRule(
                clock=clock,
                ttl_seconds=int(sub.get("ttl_seconds", 300)),
                max_entries=int(sub.get("max_entries", 100_000)),
            )

        def _build_freshness() -> RiskRule:
            sub = params.for_rule("SignalFreshnessRule")
            return SignalFreshnessRule(max_age_seconds=int(sub.get("max_age_seconds", 30)))

        def _build_whitelist() -> RiskRule:
            sub = params.for_rule("SymbolWhitelistRule")
            symbols = sub.get("symbols", [])
            return SymbolWhitelistRule(symbols=symbols)

        def _build_strategy_paused() -> RiskRule:
            return StrategyPausedRule(state_reader=self._strategy_state_reader)

        def _build_per_order_size_cap() -> RiskRule:
            sub = params.for_rule("PerOrderSizeCap")
            max_pct = Decimal(str(sub.get("max_pct_of_equity", "0.05")))
            return PerOrderSizeCap(equity_reader=self._ledger, max_pct_of_equity=max_pct)

        def _build_strategy_budget_cap() -> RiskRule:
            return StrategyBudgetCap(ledger_reader=self._ledger)

        def _build_symbol_concentration_cap() -> RiskRule:
            return SymbolConcentrationCap(ledger_reader=self._ledger)

        def _build_throttle_scaler() -> RiskRule:
            sub = params.for_rule("ThrottleScaler")
            scaler = Decimal(str(sub.get("scaler", "1.0")))
            return ThrottleScaler(scaler=scaler)

        def _build_price_sanity() -> RiskRule:
            sub = params.for_rule("PriceSanityCheck")
            max_dev = Decimal(str(sub.get("max_deviation_pct", "0.05")))
            return PriceSanityCheck(max_deviation_pct=max_dev)

        def _build_capital_reservation() -> RiskRule:
            return CapitalReservationRule(reserver=self._reserver)

        builders: dict[str, RuleBuilder] = {
            "SystemStateRule": _build_system_state,
            "IdempotencyRule": _build_idempotency,
            "SignalFreshnessRule": _build_freshness,
            "SymbolWhitelistRule": _build_whitelist,
            "StrategyPausedRule": _build_strategy_paused,
            "PerOrderSizeCap": _build_per_order_size_cap,
            "StrategyBudgetCap": _build_strategy_budget_cap,
            "SymbolConcentrationCap": _build_symbol_concentration_cap,
            "ThrottleScaler": _build_throttle_scaler,
            "PriceSanityCheck": _build_price_sanity,
            "CapitalReservationRule": _build_capital_reservation,
        }

        rules: list[RiskRule] = []
        for name in config.rules.enabled:
            builder = builders.get(name)
            if builder is None:
                raise ValueError(f"unknown rule in config.rules.enabled: {name}")
            rules.append(builder())
        return rules

    # ===== 內部元件 read-only 暴露（測試與 observability 用） =====

    @property
    def state(self) -> SystemState:
        return self._state_machine.state

    @property
    def state_machine(self) -> StateMachine:
        return self._state_machine

    @property
    def reserver(self) -> CapitalReserver:
        return self._reserver

    @property
    def config(self) -> RiskConfig:
        return self._config

    @property
    def is_started(self) -> bool:
        return self._started and not self._stopped

    def warming_up_remaining_seconds(self) -> float:
        """測試與 observability 用：暖機期剩餘秒數，0 代表已結束。"""
        return self._warming_up_remaining()


class _AlwaysActiveStateReader:
    """預設 StrategyStateReader：所有 strategy 視為 ACTIVE。

    當 RiskGate 未注入真實 state_reader（例如測試或單元場景）時的預設值。
    結構性符合 risk.ports.StrategyStateReader Protocol。
    """

    def get_state(self, strategy_id: str) -> str | None:
        return "ACTIVE"
