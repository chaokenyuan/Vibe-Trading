## Context

成交回報處理是「訊號 → 訂單」鏈路的最後一環。FillProcessor 必須：
1. 解 client_order_id → strategy_id
2. 套到正確的 LogicalBook
3. 維持 broker 視角的真實持倉
4. 提供 PositionReader 給 risk-gate 消費

## Goals / Non-Goals

### Goals

1. FillProcessor 為 stateless 純編排，所有狀態在 LogicalBook / BrokerPositionTracker
2. BookPositionReader 滿足 risk.ports.PositionReader Protocol
3. MockFillSource 可手動 push Fill 供測試完整 fill 鏈

### Non-Goals

1. 不實作真 WebSocket 訂閱
2. 不做 PnL 計算（unrealized/realized）
3. 不做 reservation_id 釋放（mapping 涉及多 capability，留後續 change）
4. 不做 broker 對帳（broker reports vs internal book diff，留後續 change）

## Decisions

### D-1：BrokerPositionTracker 派生自 LogicalBook

**決策**：BrokerPositionTracker 不獨立持有狀態，而是「sum of strategies' LogicalBook positions」on demand。

**理由**：
- 真相只有一份（LogicalBook），broker 視角是衍生資料
- 不需處理同步問題
- E2 logical books 凍結決策一致

### D-2：FillSource 為 push（async event）而非 pull

**決策**：FillSource.start 啟動 async task；fill 透過注入的 callback 推送。

**替代方案**：pull-based（呼叫端 poll）：交易所多為 WebSocket push，pull 模式語意不對

**理由**：未來 ccxt WebSocket 自然就是 push；mock 也可隨時手動 push。

### D-3：本 change 不做 reservation 釋放

**決策**：FillProcessor 處理 LogicalBook 更新，但不呼叫 CapitalReserver.release。

**替代方案**：在 FillProcessor 加 reservation 釋放：需要 client_order_id → reservation_id mapping，涉及修改 OrderSubmitted 事件加 reservation_id

**理由**：
- 本 change 範圍已包含 LogicalBook + BrokerBook + PositionReader 三件事
- reservation 釋放是獨立議題，留後續 `add-reservation-release-bridge` change
- MVP 上線時 risk-gate 的 reservation 仍可由人工或定時器清空

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| **R-1** Fill 對應的 strategy_id 在 registry 不存在 | 紀錄 warning，不更新 LogicalBook（broker 收到 fill 但無對應策略代表上游有 bug） |
| **R-2** client_order_id 解碼失敗 | 紀錄 error 事件供告警；不嘗試猜測 |
| **R-3** Broker 重送同 fill_id | FillProcessor 內部 fill_id 去重快取（LRU） |
