## Why

`signal-ingestion` 已能接收訊號並透過 `SignalConsumer` Protocol 交給下游，但目前無人實作 SignalConsumer；`risk-gate` 雖完整但未串接到流程。本 change 補上中間樞紐：把 Signal 路由到對應策略、產生 OrderIntent、過 RiskGate、送往 OrderSink。

依 design-brief 第 10 節的 Capability 撰寫順序，此為第一批的最後一項。

## What Changes

- **新增** `strategy-host` capability 提供：
  - `Strategy` Protocol：`async on_signal(signal) -> list[OrderIntent]`
  - `StrategyState` 列舉：LOADED / ACTIVE / PAUSED / LIQUIDATING / STOPPED / FAILED
  - `LogicalBook` 類：每策略獨立帳本（追蹤 positions、記錄 fill）
  - `StrategyRegistry` 完整實作（取代 signal-ingestion 的 stub）
  - `StrategyHost` 編排器：實作 `SignalConsumer`，串接 RiskGate 與 OrderSink
  - `PassthroughStrategy` 示範實作（1:1 Signal → OrderIntent，無內部邏輯）
  - `OrderSink` Protocol 與 `Fill` 值物件作為與後續 order-execution / reconciliation 的契約

- **跨 capability 整合**：
  - 取代 `signals.registry_stub.InMemoryStrategyRegistry`：由 `strategies/registry.py` 提供完整版
  - `StrategyHost` 為 `SignalConsumer`：接 `SignalRouter.subscribe()`
  - `StrategyHost` 持有 `RiskGate` 引用：通過 `evaluate(intent)` 取得 Decision
  - `StrategyHost` 持有 `OrderSink`：APPROVE 即 submit

### 範圍外（留給後續 change）

- 真實 CCXT 下單實作（屬 `add-order-execution`）
- 持倉對帳 / 釋放 Reservation（屬 `add-reconciliation`）
- 策略熱載入（E3 凍結為「重啟才換」）
- 多市場資金分配演算法（已凍結為共池 + 軟上限）

## Capabilities

### New Capabilities

- `strategy-host`：策略運行容器與訊號到訂單的轉換樞紐

### Modified Capabilities

無（取代 signal-ingestion 內部 stub 不算 spec-level 變更）。

## Impact

新模組 `strategies/`：

```
strategies/
├── __init__.py
├── types.py       StrategyState、LogicalPosition、Fill、ClientOrderId
├── ports.py       Strategy Protocol、OrderSink Protocol
├── book.py        LogicalBook
├── registry.py    StrategyRegistry（完整版）
├── host.py        StrategyHost
└── strategies/    具體 Strategy 實作集
    └── passthrough.py
```

依賴：無新外部依賴。

對未來 capability 承諾：

- `add-order-execution` 將提供 `OrderSink` 具體實作
- `add-reconciliation` 將消費 `Fill`、呼叫 `LogicalBook.apply_fill` 與 `CapitalReserver.release`
- `add-observability` 將訂閱 strategy-host 發布的事件（後續加事件型別）
