# add-risk-rules-impl — 驗收紀錄

## 驗證

```
$ openspec validate add-risk-rules-impl → valid
$ mypy → 120 source files clean
$ pytest -q → 371 passed
$ ruff check → All clean
```

## Spec scenario 對測試對照

每條規則對應測試：

| Rule | 主測試 |
|------|--------|
| SignalFreshnessRule | `test_rules_impl.py::test_freshness_within_threshold_passes`, `test_freshness_exceeds_threshold_rejected` |
| SymbolWhitelistRule | `test_whitelist_empty_accepts_all`, `test_whitelist_in_list_passes`, `test_whitelist_not_in_list_rejected` |
| StrategyPausedRule | `test_strategy_paused_active_passes`, `test_strategy_paused_paused_rejected`, `test_strategy_paused_unknown_rejected` |
| PerOrderSizeCap | `test_per_order_cap_clamps_when_size_exceeds`, `test_per_order_cap_passes_within_limit`, `test_per_order_cap_uses_market_when_price_none` |
| StrategyBudgetCap | `test_strategy_budget_cap_clamps`, `test_strategy_budget_cap_passes_within_limit` |
| SymbolConcentrationCap | `test_symbol_concentration_clamps`, `test_symbol_concentration_unbounded_for_unknown_symbol` |
| ThrottleScaler | `test_throttle_scaler_default_passes`, `test_throttle_scaler_clamps_when_below_one` |
| PriceSanityCheck | `test_price_sanity_market_order_passes`, `test_price_sanity_within_deviation_passes`, `test_price_sanity_over_deviation_rejected`, `test_price_sanity_zero_last_passes` |
| CapitalReservationRule | `test_capital_reservation_success_metadata_has_reservation_id`, `test_capital_reservation_failure_rejects`, `test_capital_reservation_sync_evaluate_raises` |

Engine 抽 reservation_id 由既有 RuleEngine 測試 + e2e 隱含覆蓋（既有測試套件全綠即代表 engine 行為一致）。

## 影響範圍

- **REMOVED risk-gate**：「未實作規則須提供契約 stub」requirement 移除
- **ADDED risk-gate**：9 個新 requirement（每條規則的具體行為）
- 新增程式碼 ~600 行（9 規則檔 + 引擎 reservation_id 抽取 + gate 注入）
- 移除 risk/rules/_stubs.py、tests/test_rule_stubs.py

既有測試 100% 通過（不含已刪除的 stub 測試）：347 passed → 371 passed。
