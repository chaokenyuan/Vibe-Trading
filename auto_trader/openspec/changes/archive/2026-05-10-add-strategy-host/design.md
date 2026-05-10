## Context

策略主機 (StrategyHost) 是 vibe-auto-trader 的「中間樞紐」：上游接 signal-ingestion 的 Signal，下游接 risk-gate 與 order-execution。本 change 一次串起：

```
SignalRouter → StrategyHost (SignalConsumer)
                 ↓
              Strategy.on_signal → list[OrderIntent]
                 ↓
              RiskGate.evaluate
                 ↓
              OrderSink.submit  (APPROVE 才送)
```

當前狀態：

- risk-gate 完整、signal-ingestion 完整、SignalConsumer / OrderSink Protocol 尚未有具體實作
- StrategyRegistry 在 signal-ingestion 為 in-memory stub，本 change 提供完整版本
- LogicalBook、Fill 等概念在 design-brief 第 7 節已定義

## Goals / Non-Goals

### Goals

1. 把 SignalConsumer 串到 RiskGate.evaluate + OrderSink.submit 形成完整訂單路徑
2. 凍結 Strategy Protocol：`async on_signal` 為主介面；後續 strategy 實作只填內部邏輯
3. 凍結 OrderSink Protocol 與 Fill 值物件：作為 order-execution / reconciliation 的整合契約
4. LogicalBook 提供持倉視角，可被 PositionReader 介面消費（與 risk-gate 整合點）
5. 同 signal_id 跨多 strategy 路由：依 signal.strategy_id 派送至對應 strategy

### Non-Goals

1. 不實作真實下單 SDK（CCXT 等）
2. 不執行對帳（Fill 處理由 reconciliation）
3. 不支援策略熱載入（E3 凍結）
4. 不在本 change 跑端到端含外部交易所的 e2e

## Decisions

### D-1：StrategyHost 為 SignalConsumer 唯一具體實作

**決策**：本 change 提供一個 `StrategyHost` 類，同時擔任 SignalConsumer 與 OrderSink 客戶端。

**替代方案**：
- 拆成 SignalDispatcher + OrderRouter：過度工程，本層 SRP 邊界不需要進一步拆分
- StrategyHost 只負責 dispatch、另寫 RiskGateProxy：增加類別數無對應好處

**理由**：StrategyHost 的職責就是「把訊號變成可執行的訂單」，這是一個職責不是兩個。

### D-2：Strategy.on_signal 回傳 list 而非 yield

**決策**：`async def on_signal(signal) -> list[OrderIntent]` 而非 AsyncIterator。

**替代方案**：
- AsyncIterator：streaming 場景有用，但 Strategy 通常一筆訊號產 0–N 筆訂單，回 list 即可

**理由**：簡單、可測試（直接比對 list）、符合大多數策略模式（Signal-to-Orders 是純函式映射）。

### D-3：LogicalBook 為 mutable 但 thread-safe 並非必須

**決策**：LogicalBook 為 mutable class（不是 frozen dataclass）。並發保護由 StrategyHost 在 asyncio 單一事件迴圈內保證。

**替代方案**：immutable `LogicalBook`、每次更新建新實例：違反 Python 慣例、性能差

**理由**：asyncio 單執行緒；Strategy 的 on_signal 是 async 函式，apply_fill 由 reconciliation 同樣在事件迴圈內呼叫，無 race。

### D-4：OrderSink 與 Fill 跨 capability 契約放在 strategies/

**決策**：`OrderSink` Protocol 與 `Fill` 值物件定義在 `strategies/ports.py` 與 `strategies/types.py`，後續 `order-execution` / `reconciliation` 引用。

**替代方案**：放各自 capability 的 ports：本 change 無人定義就會建構失敗

**理由**：strategies 是首個需要這兩個契約的 capability，由它「先寫 stub 形式」凍結介面，類似 signal-ingestion 提供 StrategyRegistry stub 一樣。

### D-5：client_order_id 編碼策略 ID 與訊號 ID

**決策**：`client_order_id = f"{strategy_id}.{signal_id_short}.{seq}"`，其中 `signal_id_short` 是 signal_id 前 12 字元 hex。

**理由**：OrderSink 與 Fill 都需這個編碼；reconciliation 透過解碼可把 fill 對應回 strategy。

### D-6：Strategy 執行錯誤策略狀態為 FAILED

**決策**：Strategy.on_signal 拋例外時：
- StrategyHost catch 例外並 logger.exception
- 該 strategy 狀態變為 FAILED
- 後續訊號不再 route 至該 strategy
- 持倉凍結（E4 凍結：crash 不自動平倉，等人工）

#### Scenario: Strategy crash 後不再收新訊號

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| **R-1** RiskGate 暖機期內收到訊號 | 訊號被 RiskGate 拒（已 spec 過）；StrategyHost 接到 Decision=REJECT 即不送 OrderSink，正常路徑 |
| **R-2** OrderSink 故障 | StrategyHost catch + 紀錄 + 該訊號 RuleVerdict 標記為 deferred；不影響其他訊號 |
| **R-3** Strategy 一直拋例外 | crash → FAILED 狀態，後續訊號自動 skip，避免雪崩 |
| **R-4** 多 strategy 同時被觸發大量訊號 | asyncio 單執行緒序列化處理；性能不夠時再升 worker pool |

## Open Questions

1. **on_fill 是否在本 change 提供**：reconciliation 才有 Fill 來源，本 change 先在 Strategy Protocol 預留 `async on_fill(fill)` 方法（預設 no-op），實際呼叫由 reconciliation 串
2. **Strategy 啟停時機**：start 為「Registry 加完並 RiskGate 啟好」之後；本 change StrategyHost 不主動 start strategy，由 deployment 層編排
