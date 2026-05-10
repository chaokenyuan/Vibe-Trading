## Why

`strategy-host` 透過 `OrderSink` Protocol 把 APPROVE 的 OrderIntent 送出，但目前無人實作 OrderSink。本 change 提供 `ExchangeOrderSink` 具體實作 + `ExecutionAdapter` 抽象（封裝交易所 SDK），讓系統能真正下單。

## What Changes

- **新增** `execution` capability（套件 `execution/`）：
  - `ExecutionAdapter` Protocol：抽象交易所 SDK（submit/cancel）
  - `ExchangeOrderSink`：實作 `strategies.ports.OrderSink`，內部以 ExecutionAdapter 完成實際下單
  - `MockExecutionAdapter`：測試用，可預設成功/失敗、自動產 Fill
  - `CcxtExecutionAdapter`：使用 ccxt SDK 對接 100+ 交易所；本 change 為 stub（簽名凍結，呼叫即拋 NotImplementedError；後續 change 視部署目標填內部）
- 新增事件：`OrderSubmitted`、`OrderRejectedByBroker`（不影響既有 risk-gate 事件）
- 新增配置：`config/execution.yaml`（broker 選擇、API key 環境變數名稱、testnet flag）

### 範圍外

- 真實 ccxt SDK 整合（保留 stub，後續 change 視部署交易所）
- WebSocket 訂單簿訂閱
- 限價單時間在場（time-in-force）等進階訂單類型
- Fill 處理 / 釋放 reservation（屬 reconciliation）

## Capabilities

### New Capabilities

- `order-execution`：訂單執行層

### Modified Capabilities

無。

## Impact

新模組 `execution/`：

```
execution/
├── __init__.py
├── types.py           BrokerOrder、ExecutionResult
├── ports.py           ExecutionAdapter Protocol
├── events.py          OrderSubmitted、OrderRejectedByBroker
├── sink.py            ExchangeOrderSink（OrderSink 實作）
├── config.py          ExecutionConfig
└── adapters/
    ├── mock.py        MockExecutionAdapter（測試 + 開發 dry-run）
    └── ccxt_stub.py   CcxtExecutionAdapter stub
```

依賴：暫無新外部依賴（ccxt 為 stub 階段不引入）。

對未來 capability 承諾：
- `add-reconciliation` 將消費 OrderSubmitted 與 Fill 事件
- `add-observability` 將訂閱 broker 失敗事件供告警
