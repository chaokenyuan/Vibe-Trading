## Why

當前 `risk-gate.CapitalReserver` 有 `release()` API 但無人呼叫——`reconciliation.FillProcessor` 處理 fill 時不知道對應的 `reservation_id`，因為 fill 帶的是 `client_order_id` 而非 reservation_id。本 change 補上「client_order_id ↔ reservation_id」對應與自動釋放邏輯。

延伸：`add-reconciliation` 提案的範圍外明確列為「Capital reservation 釋放（client_order_id → reservation_id mapping 涉及多 capability 串接，本 change 預留 hook 不直接實作）」，現由本 change 補上。

## What Changes

- **修改** `order-execution`（既有 `OrderSubmitted` 事件加 `reservation_id: UUID | None` 欄位）：
  - `ExchangeOrderSink.submit` 把 `decision.reservation_id` 寫入新發布的 `OrderSubmitted`
  - 既有 scenario 仍通過（向下相容，欄位帶 None 不影響）

- **新增** `reservation-release` capability（套件 `reservation_bridge/`）：
  - `ReservationBridge`：訂閱事件 + 內部 mapping
  - 訂閱 `OrderSubmitted` → 紀錄 `client_order_id → reservation_id`
  - 訂閱 `OrderRejectedByBroker` → 立即釋放對應 reservation
  - 訂閱 `FillProcessed` → 釋放對應 reservation
  - mapping 採 LRU + TTL（避免長期累積）

### 範圍外

- 不修改 risk-gate.Decision 結構
- 不修改 reconciliation.FillProcessor 行為（仍只處理 LogicalBook 與 fill_id 去重）
- 不處理 partial fill 的部分釋放（MVP 全 release）

## Capabilities

### New Capabilities

- `reservation-release`：reservation 自動釋放橋接器

### Modified Capabilities

- `order-execution`：`OrderSubmitted` 事件新增 `reservation_id` 欄位

## Impact

新模組：

```
reservation_bridge/
├── __init__.py
├── bridge.py          ReservationBridge
└── (無 adapter，純內部協調器)
```

修改：

- `execution/events.py`：`OrderSubmitted` 加 `reservation_id: UUID | None = None`
- `execution/sink.py`：傳遞 `decision.reservation_id` 至事件

依賴：無新外部依賴。

對未來 capability 承諾：
- partial fill 部分釋放可後續 change 處理（追加 `released_qty` 與 `released_notional` 欄位）
