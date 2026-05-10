## 1. 骨架

- [x] 1.1 建立 `execution/` 套件 + `execution/adapters/`
- [x] 1.2 pyproject.toml include `execution*`

## 2. 值物件 + Protocol

- [x] 2.1 在 `execution/types.py` 定義 `ExecutionResult` 等共用型別（如有）
- [x] 2.2 在 `execution/ports.py` 定義 `ExecutionAdapter` Protocol（runtime_checkable）

## 3. 事件

- [x] 3.1 在 `execution/events.py` 定義 `OrderSubmitted`、`OrderRejectedByBroker`（繼承 Event）
- [x] 3.2 撰寫事件不可變 + 序列化測試

## 4. ExchangeOrderSink

- [x] 4.1 在 `execution/sink.py` 實作 `ExchangeOrderSink`：注入 adapter + publisher
- [x] 4.2 submit 流程：呼叫 adapter → 發 OrderSubmitted；失敗發 OrderRejectedByBroker + re-raise
- [x] 4.3 撰寫測試覆蓋 spec scenario

## 5. Adapters

- [x] 5.1 `execution/adapters/mock.py`：MockExecutionAdapter（含 submitted log + fail_next toggle）
- [x] 5.2 `execution/adapters/ccxt_stub.py`：CcxtExecutionAdapter stub
- [x] 5.3 撰寫 mock + stub 測試

## 6. 配置

- [x] 6.1 `execution/config.py` ExecutionConfig（broker、testnet flag）
- [x] 6.2 `config/execution.yaml` 預設範本

## 7. 整合 + 文件

- [x] 7.1 e2e 測試：StrategyHost + ExchangeOrderSink + MockExecutionAdapter 完整流程
- [x] 7.2 `execution/README.md`

## 8. 驗收

- [x] 8.1 `openspec validate add-order-execution` 通過
- [x] 8.2 mypy strict / pytest / ruff / cov ≥ 90%
- [x] 8.3 撰寫 acceptance.md
