# reconciliation capability

對帳與持倉同步：消費交易所 Fill、更新 LogicalBook、提供 PositionReader 給 risk-gate。

## 模組結構

```
reconciliation/
├── ports.py              FillSource Protocol（async start/stop, push 模式）
├── events.py             FillProcessed
├── processor.py          FillProcessor（核心 fill 處理 + 去重）
├── broker_book.py        BrokerPositionTracker（派生自 LogicalBooks）
├── position_reader.py    BookPositionReader（risk.ports.PositionReader 實作）
└── adapters/
    ├── mock.py           MockFillSource（測試 / dry-run）
    └── ccxt_stub.py      CcxtFillSource stub
```

## 流程

```
Exchange WebSocket → CcxtFillSource (stub) → FillProcessor.on_fill
                                              ├── 解 client_order_id → strategy_id
                                              ├── registry.get_book → LogicalBook
                                              ├── apply_fill (加減倉、avg_entry)
                                              ├── publish FillProcessed
                                              └── fill_id 寫入去重快取
```

## 對外介面

```python
from reconciliation.processor import FillProcessor
from reconciliation.broker_book import BrokerPositionTracker
from reconciliation.position_reader import BookPositionReader
from reconciliation.adapters.mock import MockFillSource

processor = FillProcessor(registry=strategy_registry, publisher=publisher, clock=clock)
fill_source = MockFillSource(callback=processor.on_fill)
broker_tracker = BrokerPositionTracker(registry=strategy_registry)
position_reader = BookPositionReader(registry=strategy_registry)

# position_reader 可直接傳給 RiskGate
await fill_source.start()
```

## 設計筆記

- BrokerPositionTracker 不持狀態，直接派生自所有 LogicalBook（Single Source of Truth = LogicalBook）
- FillProcessor 對同 fill_id 冪等（broker 重送不會重複套用）
- 未知 strategy_id 的 fill 紀錄 warning 不更新（代表上游有 bug）

## 已知限制（MVP）

- CcxtFillSource 為 stub，後續 change 視部署交易所實作 WebSocket 訂閱
- 不釋放 CapitalReserver reservation（client_order_id → reservation_id mapping 需後續 change 補）
- 不計算 PnL / 不做 broker 對帳（broker reports vs internal book diff）

## 後續 change 預告

- `add-reservation-release-bridge`：建立 client_order_id → reservation_id mapping，自動釋放 reservation
- `add-pnl-calculation`：unrealized + realized PnL
- `add-broker-reconciliation`：定期跟交易所 positions 對帳
