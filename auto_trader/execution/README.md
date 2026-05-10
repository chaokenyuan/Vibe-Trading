# order-execution capability

訂單執行層：實作 `strategies.ports.OrderSink`，把 APPROVE 的 OrderIntent 真正送到交易所。

## 模組結構

```
execution/
├── ports.py           ExecutionAdapter Protocol
├── events.py          OrderSubmitted、OrderRejectedByBroker
├── sink.py            ExchangeOrderSink（OrderSink 實作）
├── config.py          ExecutionConfig
└── adapters/
    ├── mock.py        MockExecutionAdapter（測試 / dry-run）
    └── ccxt_stub.py   CcxtExecutionAdapter（stub，後續 change 填 ccxt 真實邏輯）
```

## 對外進入點

```python
from execution.adapters.mock import MockExecutionAdapter
from execution.sink import ExchangeOrderSink

adapter = MockExecutionAdapter()  # 或未來的 CcxtExecutionAdapter(...)
sink = ExchangeOrderSink(adapter=adapter, publisher=event_publisher, clock=clock)

# 把 sink 傳給 StrategyHost
host = StrategyHost(registry=..., risk_gate=..., order_sink=sink)
```

## 流程

```
StrategyHost.submit
   ↓
ExchangeOrderSink.submit
   ├── adapter.submit → broker_order_id 或 raise
   ├── 成功 → publish(OrderSubmitted)
   └── 失敗 → publish(OrderRejectedByBroker) + re-raise
```

## Adapter 對照

| Adapter | 狀態 | 用途 |
|---------|------|------|
| `MockExecutionAdapter` | 完整 | 測試、dry-run、本機開發 |
| `CcxtExecutionAdapter` | stub | 後續 change 整合 100+ 交易所 |

## API key 管理

`config/execution.yaml` 不直接寫 API key；改寫環境變數名稱（`api_key_env`、`api_secret_env`），由部署層注入。

## 後續 change 預告

- 實作 `CcxtExecutionAdapter` 串接 Binance / OKX / Bybit
- WebSocket 訂單回報串流（補 Fill 來源給 reconciliation）
- 訂單追蹤（cancel-and-replace、partial fill 處理）
