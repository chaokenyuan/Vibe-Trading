## ADDED Requirements

### Requirement: FillProcessor 處理 Fill 並更新 LogicalBook

`FillProcessor` SHALL 提供 `async on_fill(fill: Fill)` 處理流程：

1. 解 fill.client_order_id 取得 strategy_id
2. 從 StrategyRegistry 取得對應 LogicalBook
3. 呼叫 LogicalBook.apply_fill(fill)
4. 發布 `FillProcessed` 事件
5. 內部維護 fill_id 去重快取，重複 fill_id 直接跳過

#### Scenario: 已知策略的 Fill 更新 LogicalBook

- **WHEN** Fill 帶 client_order_id="A.x.1"，registry 含 strategy A
- **THEN** A 的 LogicalBook SHALL 含對應 position
- **AND** EventPublisher SHALL 收到 FillProcessed 事件

#### Scenario: 未知策略的 Fill 跳過

- **WHEN** Fill 帶 client_order_id="UNKNOWN.x.1"
- **THEN** 不更新任何 LogicalBook
- **AND** 紀錄 warning（可由 logger.warning 觀察）

#### Scenario: 重複 fill_id 去重

- **WHEN** 同 fill_id 連續送入 FillProcessor 兩次
- **THEN** 第二次 SHALL 不更新 LogicalBook
- **AND** 不發布第二次 FillProcessed

---

### Requirement: BrokerPositionTracker 派生自 LogicalBook

`BrokerPositionTracker` SHALL 提供 `get_total_position(symbol) -> Decimal`，回傳所有策略對該 symbol 的 LogicalBook 持倉總和。

#### Scenario: 多策略同 symbol 持倉相加

- **WHEN** strategy A LogicalBook BTC qty=1，strategy B LogicalBook BTC qty=-0.5
- **THEN** tracker.get_total_position("BTCUSDT") SHALL 回 0.5

#### Scenario: 無持倉回 0

- **WHEN** 無策略持有 ETH
- **THEN** tracker.get_total_position("ETHUSDT") SHALL 回 0

---

### Requirement: BookPositionReader 滿足 risk.ports.PositionReader

`BookPositionReader` SHALL 實作 `risk.ports.PositionReader`，使 risk-gate 可透過此介面讀取 LogicalBook 的 read-only 視圖。

#### Scenario: 結構性符合 PositionReader

- **WHEN** `isinstance(BookPositionReader(...), PositionReader)`
- **THEN** SHALL 回 True

#### Scenario: get_position 回對應 LogicalPosition

- **WHEN** strategy A 持有 BTC
- **THEN** reader.get_position("A", "BTCUSDT") SHALL 回 strategy A 的 LogicalPosition

#### Scenario: list_positions 列出所有策略持倉

- **WHEN** registry 含多個 strategy 各自有持倉
- **THEN** reader.list_positions() SHALL 回所有策略所有 symbol 的 LogicalPosition

---

### Requirement: FillSource Protocol + MockFillSource + Stub

`FillSource` SHALL 為 Protocol（async start/stop）。
`MockFillSource` SHALL 提供 `push(fill)` 手動推送，符合 FillSource Protocol。
`CcxtFillSource` 為 stub，呼叫 start 即拋 NotImplementedError。

#### Scenario: MockFillSource 手動推送觸發 callback

- **WHEN** Mock 注入 callback 後呼叫 push(fill)
- **THEN** callback SHALL 被呼叫一次

#### Scenario: CcxtFillSource stub 拋 NotImplementedError

- **WHEN** 呼叫 CcxtFillSource().start()
- **THEN** SHALL 拋 NotImplementedError
