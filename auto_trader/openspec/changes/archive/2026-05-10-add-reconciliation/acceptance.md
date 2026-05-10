# add-reconciliation — 驗收紀錄

## 驗證

```
$ openspec validate add-reconciliation → valid
$ mypy risk/ signals/ strategies/ execution/ reconciliation/ tests/ → 99 source files clean
$ pytest -q → 367 passed
$ ruff check → All clean
```

## Spec scenario 對測試對照

| Requirement | 覆蓋測試 |
|-------------|---------|
| FillProcessor 已知策略更新 LogicalBook | `test_reconciliation.py::test_fill_updates_logical_book` |
| FillProcessor 未知策略跳過 | `test_reconciliation.py::test_fill_unknown_strategy_skipped` |
| FillProcessor 重複 fill_id 去重 | `test_reconciliation.py::test_duplicate_fill_id_skipped` |
| BrokerPositionTracker 多策略相加 | `test_reconciliation.py::test_broker_tracker_sums_strategies` |
| BrokerPositionTracker 無持倉回 0 | `test_reconciliation.py::test_broker_tracker_no_position_returns_zero` |
| BookPositionReader 結構性符合 PositionReader | `test_reconciliation.py::test_book_position_reader_satisfies_protocol` |
| BookPositionReader 取持倉 | `test_reconciliation.py::test_book_reader_returns_positions` |
| MockFillSource push triggers callback | `test_reconciliation.py::test_mock_fill_source_push_triggers_callback` |
| CcxtFillSource stub 拋 NotImplementedError | `test_reconciliation.py::test_ccxt_fill_source_stub_raises` |

## 後續 change 預告

- `add-reservation-release-bridge`：完整實作 client_order_id → reservation_id 自動釋放
- `add-pnl-calculation`：unrealized + realized PnL
- 真實 ccxt WebSocket fill source 實作
