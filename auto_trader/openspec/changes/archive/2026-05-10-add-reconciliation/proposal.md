## Why

訂單已能透過 `add-order-execution` 送出，但成交回報（Fill）尚無人處理：LogicalBook 不會更新、broker 視角無從追蹤、capital reservation 不會釋放。本 change 補上對帳與持倉同步。

## What Changes

新增 `reconciliation` capability（套件 `reconciliation/`）：

- `FillSource` Protocol：訂閱交易所 Fill 串流的抽象（async start/stop）
- `MockFillSource`：測試與 dry-run 用，可手動 push Fill
- `CcxtFillSource`：stub，後續 change 接 ccxt WebSocket
- `FillProcessor`：核心 fill 處理邏輯
  - 解碼 client_order_id 取得 strategy_id
  - 取得對應 LogicalBook 並呼叫 apply_fill
  - 發布 `FillProcessed` 事件
- `BrokerPositionTracker`：維護 broker 視角的真實持倉（= sum of LogicalBooks per symbol）
- `BookPositionReader`：實作 `risk.ports.PositionReader`，從 StrategyRegistry 與 BrokerPositionTracker 提供 read-only 視圖

### 範圍外

- 真實 ccxt WebSocket 訂閱（保留 stub，依部署交易所獨立 change）
- Capital reservation 釋放（client_order_id → reservation_id mapping 涉及多 capability 串接，本 change 預留 hook 不直接實作）
- PnL 計算（unrealized / realized）
- 手續費攤銷

## Capabilities

### New Capabilities

- `reconciliation`：對帳與持倉同步

### Modified Capabilities

無。

## Impact

新模組：

```
reconciliation/
├── types.py         BrokerPosition、ReconciliationStats
├── ports.py         FillSource Protocol
├── events.py        FillProcessed、ReconciliationDrift（後者保留 hook）
├── processor.py     FillProcessor
├── broker_book.py   BrokerPositionTracker
├── position_reader.py  BookPositionReader
└── adapters/
    ├── mock.py      MockFillSource
    └── ccxt_stub.py CcxtFillSource stub
```

依賴：無新外部依賴。

對未來 capability 承諾：
- 後續可加 `add-reservation-release-bridge`：完整實作 client_order_id → reservation_id mapping
- 後續真實 ccxt WebSocket adapter
