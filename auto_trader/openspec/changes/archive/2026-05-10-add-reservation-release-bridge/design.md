## Context

目前流程：
- StrategyHost 收 Decision（含 reservation_id）→ 編 client_order_id → sink.submit
- ExchangeOrderSink 發 OrderSubmitted（不含 reservation_id）
- FillProcessor 收 fill（含 client_order_id）→ apply_fill 但不釋放 reservation

斷點：fill 來時無從得知 reservation_id。

## Goals

1. 自動釋放：reject/fill 即釋放 reservation
2. 不破壞既有 spec：MODIFIED 區塊清楚描述 OrderSubmitted 欄位增加
3. mapping 不無限增長：LRU + TTL 守
4. 故障容錯：CapitalReserver.release 失敗紀錄 error 不影響其他事件處理

## Non-Goals

- 不處理 partial fill 部分釋放
- 不處理 fill notional ≠ reserved notional 的對帳偏差（後續 change）
- 不在 fill 來時校正 reservation 數量

## Decisions

### D-1：OrderSubmitted 加 reservation_id 欄位

**決策**：加 `reservation_id: UUID | None = None`。預設 None 保留與既有測試相容。

**替代**：
- 另發 `OrderRouted` 事件：多一個事件型別，但更清楚 SRP
- 修改 Decision：Decision 已 archived，動歷史 spec 風險高

**理由**：OrderSubmitted 已是「訂單到達 broker」的時間點，附帶 reservation_id 語意自然。

### D-2：Bridge 為單例 + asyncio 序列化

**決策**：與其他寫者單例（RiskGate、StateMachine）一致，在 asyncio 事件迴圈內單實例運作。

**理由**：
- 不需鎖（asyncio 單執行緒）
- 與現有 publisher fan-out 模式一致

### D-3：mapping LRU + TTL

**決策**：mapping 採 OrderedDict-based LRU；TTL 預設 24 小時、上限 100k。

**理由**：
- 訂單通常數秒到數分鐘成交；24h TTL 足夠覆蓋所有正常情境
- 上限避免異常情境累積（broker 一直回報 reject 但 fill 不來）

### D-4：未知 client_order_id 的 fill 紀錄 warning 不釋放

**決策**：fill 對應不到 mapping（mapping 已過期或從未進入）→ 紀錄 warning，不嘗試釋放。

**理由**：避免亂釋放錯誤的 reservation；若 mapping 真的丟了，CapitalReserver 可由人工或定時任務清理。
