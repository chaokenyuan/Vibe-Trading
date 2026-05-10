# add-strategy-host — 驗收紀錄

## 驗證

```
$ openspec validate add-strategy-host
Change 'add-strategy-host' is valid
```

```
$ mypy risk/ signals/ strategies/ tests/
Success: no issues found in 80 source files
```

```
$ pytest -q
334 passed
```

```
$ ruff check ...
All checks passed!
```

## Spec scenario 對測試對照（精簡）

| Requirement | 覆蓋測試 |
|-------------|---------|
| Strategy Protocol | `test_strategies_host.py::test_passthrough_strategy_satisfies_protocol` |
| StrategyState enum | `test_strategies_types.py::test_strategy_state_has_six_values` |
| LogicalBook 持倉 | `test_strategies_book.py::*`（7 tests） |
| StrategyRegistry | `test_strategies_registry.py::*`（8 tests） |
| StrategyHost ACTIVE 全鏈路 | `test_strategies_host.py::test_active_strategy_signal_flows_to_order_sink` |
| StrategyHost PAUSED 跳過 | `test_strategies_host.py::test_paused_strategy_signal_skipped` |
| StrategyHost 未註冊 跳過 | `test_strategies_host.py::test_unknown_strategy_signal_skipped` |
| StrategyHost crash → FAILED | `test_strategies_host.py::test_strategy_crash_sets_state_failed_and_skips_subsequent` |
| StrategyHost RiskGate REJECT 不 submit | `test_strategies_host.py::test_risk_gate_reject_does_not_submit` |
| client_order_id 編碼 | `test_strategies_host.py::test_client_order_id_encoding_format`, `test_decode_strategy_id_helper` |
| OrderSink + Fill 契約 | `test_strategies_types.py::test_fill_*`, `test_strategies_host.py::test_recording_order_sink_satisfies_protocol` |

## 後續 change 預告

- `add-order-execution`：實作 OrderSink（基於 CCXT 或 mock），產生 Fill 事件
- `add-reconciliation`：消費 Fill，呼叫 LogicalBook.apply_fill 與 CapitalReserver.release
