## Context

訂單執行層是 vibe-auto-trader 唯一直接接觸真實金錢的元件。本 change 提供：
- 抽象介面（ExecutionAdapter）讓不同交易所 SDK 互換
- 具體實作（ExchangeOrderSink）滿足 strategy-host 需要的 OrderSink Protocol
- 測試替身（MockExecutionAdapter）讓上下游可獨立進度

## Goals / Non-Goals

### Goals

1. ExchangeOrderSink 滿足 strategies.ports.OrderSink Protocol
2. 抽象 ExecutionAdapter 讓未來可換 ccxt / 自寫 binance SDK / paper trading
3. MockExecutionAdapter 提供「成功/失敗/自動產 Fill」三種可控行為
4. OrderSubmitted / OrderRejectedByBroker 事件供 observability + reconciliation 訂閱

### Non-Goals

1. 不實作真實 ccxt（保留 stub）
2. 不處理 WebSocket 訂單回報（屬 reconciliation）
3. 不實作冪等下單（broker_order_id 由交易所回傳即唯一）
4. 不實作訂單追單／加減倉策略（屬 strategy 層）

## Decisions

### D-1：ExchangeOrderSink 為 thin wrapper，不重複交易所邏輯

**決策**：ExchangeOrderSink 只做：
1. 接受 OrderIntent + Decision + client_order_id
2. 呼叫 adapter.submit(...) 取得 broker_order_id
3. 發布 OrderSubmitted 事件
4. 失敗（adapter raise）發布 OrderRejectedByBroker 並 re-raise

**理由**：交易所差異全部留在 adapter 層；sink 邏輯穩定。

### D-2：MockExecutionAdapter 不主動產生 Fill

**決策**：MockExecutionAdapter.submit 只回傳 broker_order_id；產 Fill 留給測試或 reconciliation 觸發。

**替代方案**：submit 後立即在 publisher 發 Fill：對測試有用但模糊責任邊界

**理由**：Fill 產生屬交易所事件回報，由 reconciliation 訂閱 broker WebSocket 處理（後續 change）。本層只到 OrderSubmitted。

### D-3：ccxt adapter 為 stub

**決策**：CcxtExecutionAdapter 類存在但 submit/cancel 拋 NotImplementedError。

**理由**：實作需要真 API key + 整合測試 + 部署目標確認。先凍結介面，後續 change 視部署交易所填內部。

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| **R-1** ExecutionAdapter raise 漏接導致整個 SignalConsumer 死 | ExchangeOrderSink try/except，發布 OrderRejectedByBroker 後 re-raise；StrategyHost 已 catch sink.submit 例外 |
| **R-2** 同 client_order_id 重複 submit | 由 strategy-host 負責唯一性（已含 seq）；本層不去重 |
| **R-3** broker_order_id 未取得（網路 timeout） | adapter 應 raise；上層 catch 並可選擇重試（不在本 change） |
