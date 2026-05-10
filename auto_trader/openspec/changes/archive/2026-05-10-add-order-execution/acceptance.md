# add-order-execution — 驗收紀錄

## 驗證

```
$ openspec validate add-order-execution → valid
$ mypy risk/ signals/ strategies/ execution/ tests/ → 89 source files clean
$ pytest -q → 352 passed
$ ruff check → All clean
```

## Spec scenario 對測試對照

| Requirement | 覆蓋測試 |
|-------------|---------|
| ExecutionAdapter Protocol（mock 結構） | `test_execution.py::test_mock_satisfies_execution_adapter_protocol` |
| ExecutionAdapter Protocol（ccxt stub 結構） | `test_execution.py::test_ccxt_stub_satisfies_execution_adapter_protocol` |
| CcxtExecutionAdapter stub 拋 NotImplementedError | `test_execution.py::test_ccxt_stub_submit_raises_not_implemented`, `test_ccxt_stub_cancel_raises_not_implemented` |
| ExchangeOrderSink 結構符合 OrderSink | `test_execution.py::test_sink_satisfies_order_sink_protocol` |
| 成功 submit 發布 OrderSubmitted | `test_execution.py::test_sink_success_emits_order_submitted` |
| adapter 失敗發布 OrderRejectedByBroker + re-raise | `test_execution.py::test_sink_failure_emits_rejected_and_reraises` |
| MockExecutionAdapter 預設成功唯一 ID | `test_execution.py::test_mock_submit_default_returns_unique_ids` |
| MockExecutionAdapter fail_next | `test_execution.py::test_mock_fail_next_raises` |
| MockExecutionAdapter 紀錄 | `test_execution.py::test_mock_records_all_submits` |
| 事件不可變 + 序列化 | `test_execution.py::test_order_submitted_immutable`, `test_order_submitted_serializable`, `test_order_rejected_serializable` |

## 後續 change 預告

- `add-reconciliation`：消費 OrderSubmitted、訂閱交易所 Fill、釋放 Reservation、更新 LogicalBook
- 真實 ccxt adapter 實作（依部署交易所獨立 change）
