## 1. Ports

- [x] 1.1 在 `risk/ports.py` 加 `StrategyStateReader`、`EquityReader`、`ReservationLedgerReader` Protocols（runtime_checkable）

## 2. 規則實作（一檔一規則）

- [x] 2.1 `risk/rules/freshness.py`：SignalFreshnessRule
- [x] 2.2 `risk/rules/whitelist.py`：SymbolWhitelistRule
- [x] 2.3 `risk/rules/strategy_paused.py`：StrategyPausedRule
- [x] 2.4 `risk/rules/per_order_size_cap.py`：PerOrderSizeCap
- [x] 2.5 `risk/rules/strategy_budget_cap.py`：StrategyBudgetCap
- [x] 2.6 `risk/rules/symbol_concentration_cap.py`：SymbolConcentrationCap
- [x] 2.7 `risk/rules/throttle_scaler.py`：ThrottleScaler（預設 no-op）
- [x] 2.8 `risk/rules/price_sanity_check.py`：PriceSanityCheck
- [x] 2.9 `risk/rules/capital_reservation.py`：CapitalReservationRule

## 3. Engine 與 Gate 整合

- [x] 3.1 `risk/engine.py`：APPROVE 時從最後一條 RuleVerdict.metadata 抽 reservation_id
- [x] 3.2 `risk/gate.py::_build_rules`：注入新規則所需依賴
- [x] 3.3 `risk/rules/_stubs.py` 與 `tests/test_rule_stubs.py` 移除

## 4. 測試

- [x] 4.1 `tests/test_rule_freshness.py`
- [x] 4.2 `tests/test_rule_whitelist.py`
- [x] 4.3 `tests/test_rule_strategy_paused.py`
- [x] 4.4 `tests/test_rule_per_order_size_cap.py`
- [x] 4.5 `tests/test_rule_strategy_budget_cap.py`
- [x] 4.6 `tests/test_rule_symbol_concentration_cap.py`
- [x] 4.7 `tests/test_rule_throttle_scaler.py`
- [x] 4.8 `tests/test_rule_price_sanity_check.py`
- [x] 4.9 `tests/test_rule_capital_reservation.py`
- [x] 4.10 e2e：完整 11 條規則啟用情境

## 5. 驗收

- [x] 5.1 mypy / pytest / ruff 全綠
- [x] 5.2 acceptance.md
