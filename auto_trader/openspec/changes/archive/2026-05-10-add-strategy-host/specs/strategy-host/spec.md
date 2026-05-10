## ADDED Requirements

### Requirement: Strategy 為 async Protocol 接收 Signal 產生 OrderIntent

`Strategy` SHALL 為 Protocol，包含：

- `strategy_id: str`（class/instance attribute）
- `metadata: StrategyMetadata`（同 signals.types.StrategyMetadata）
- `async on_signal(signal: Signal) -> list[OrderIntent]`：核心轉換
- `async on_fill(fill: Fill) -> None`：收到自家成交回報（預設 no-op）

#### Scenario: 結構性符合 Strategy Protocol

- **WHEN** 任一具體實作含上述屬性與方法
- **THEN** SHALL 經 `isinstance(impl, Strategy)`（runtime_checkable）回傳 True

#### Scenario: PassthroughStrategy 1:1 轉換

- **WHEN** PassthroughStrategy 收到 signal
- **THEN** SHALL 回傳一筆對應 OrderIntent（symbol/side/qty/price 直接映射）

---

### Requirement: StrategyState 列舉 6 個狀態

`StrategyState` StrEnum SHALL 含 LOADED、ACTIVE、PAUSED、LIQUIDATING、STOPPED、FAILED。

#### Scenario: enum 完整列舉

- **WHEN** 列舉 StrategyState
- **THEN** SHALL 含 6 個值

---

### Requirement: LogicalBook 追蹤每策略持倉

`LogicalBook` SHALL 提供：

- `get_position(symbol) -> LogicalPosition | None`
- `list_positions() -> list[LogicalPosition]`
- `apply_fill(fill: Fill) -> None`：依 fill side/qty 增減持倉、更新 avg_entry

`LogicalPosition` 為 frozen dataclass，含 strategy_id、symbol、qty、avg_entry、opened_at、open_signal_id。

#### Scenario: apply_fill 開倉建立 position

- **WHEN** 空 book 套用 BUY 1 BTC @65000 fill
- **THEN** get_position("BTCUSDT") SHALL 回傳 qty=1, avg_entry=65000

#### Scenario: apply_fill 加倉更新 avg_entry

- **WHEN** 既有 BTC qty=1 @65000，再套 BUY 1 BTC @67000
- **THEN** position SHALL 變為 qty=2, avg_entry=66000（加權平均）

#### Scenario: apply_fill 平倉移除 position

- **WHEN** 既有 BTC qty=1，套 SELL 1 BTC
- **THEN** get_position("BTCUSDT") SHALL 回 None

---

### Requirement: StrategyRegistry 管理策略生命週期

`StrategyRegistry` SHALL 提供：

- `register(strategy: Strategy) -> None`：註冊到 LOADED 狀態
- `set_state(strategy_id, state)`：狀態變更
- `get_strategy(strategy_id) -> Strategy | None`
- `get_state(strategy_id) -> StrategyState`
- `get_book(strategy_id) -> LogicalBook | None`
- `list_strategies() -> list[str]`
- `get_strategy_metadata(strategy_id) -> StrategyMetadata | None`（與 signals.ports.StrategyRegistryProtocol 相容）

註冊時 SHALL 自動建立空 LogicalBook。

#### Scenario: 註冊新策略狀態為 LOADED

- **WHEN** 對 registry 註冊一個新 strategy
- **THEN** get_state(strategy_id) SHALL 回傳 LOADED

#### Scenario: registry 滿足 signal-ingestion StrategyRegistryProtocol

- **WHEN** 任意 StrategyRegistry 實例被傳入 SignalRouter
- **THEN** SHALL 結構性相容，能補齊 metadata

---

### Requirement: StrategyHost 為 SignalConsumer 串接 RiskGate 與 OrderSink

`StrategyHost` SHALL 實作 `SignalConsumer.on_signal(signal)`：

1. 從 registry 取對應 strategy；不存在則 logger.warning + 跳過
2. 檢查 state == ACTIVE；非 ACTIVE 則跳過（PAUSED/LIQUIDATING/FAILED/STOPPED）
3. 呼叫 strategy.on_signal(signal)，捕捉例外 → 該 strategy 標記 FAILED
4. 對每個產出的 OrderIntent 呼叫 RiskGate.evaluate
5. Decision.verdict == APPROVE → 編碼 client_order_id 並呼叫 OrderSink.submit
6. Decision.verdict == REJECT/DEFER → 不 submit，logger.info

#### Scenario: ACTIVE 策略訊號通過全鏈路

- **WHEN** ACTIVE 策略收到訊號，RiskGate 回 APPROVE
- **THEN** OrderSink.submit SHALL 被呼叫，client_order_id 編碼 strategy_id 與 signal_id

#### Scenario: PAUSED 策略訊號跳過

- **WHEN** strategy 狀態為 PAUSED
- **THEN** strategy.on_signal SHALL 不被呼叫

#### Scenario: 未註冊 strategy 訊號跳過

- **WHEN** signal.strategy_id 在 registry 不存在
- **THEN** SHALL 不呼叫任何 strategy；記錄 warning

#### Scenario: Strategy crash 進入 FAILED

- **WHEN** strategy.on_signal 拋例外
- **THEN** registry SHALL 把該 strategy 狀態設為 FAILED
- **AND** 後續訊號 SHALL 跳過該 strategy

#### Scenario: RiskGate REJECT 不 submit

- **WHEN** Decision.verdict == REJECT
- **THEN** OrderSink.submit SHALL 不被呼叫

---

### Requirement: client_order_id 編碼 strategy_id 與 signal_id

StrategyHost SHALL 為每筆 OrderIntent 計算 `client_order_id` 格式 `{strategy_id}.{signal_id_short}.{seq}`，其中：

- `signal_id_short` 為 signal_id 前 12 字元
- `seq` 為該訊號內 OrderIntent 的序號（從 1 起）

#### Scenario: 同訊號多 OrderIntent 各帶不同 seq

- **WHEN** 一個 signal 觸發 strategy 產出 3 筆 OrderIntent
- **THEN** client_order_id SHALL 形如 `A.abc123def456.1`、`A.abc123def456.2`、`A.abc123def456.3`

---

### Requirement: OrderSink Protocol 與 Fill 值物件作為跨 capability 契約

`OrderSink` Protocol SHALL 暴露：

- `async submit(intent: OrderIntent, decision: Decision, client_order_id: str) -> str`：
  回傳 broker 的 order_id

`Fill` SHALL 為 frozen dataclass，含：

- `fill_id: UUID`
- `client_order_id: str`
- `broker_order_id: str`
- `symbol: str`
- `side: Side`
- `qty: Decimal`
- `price: Decimal`
- `fees: Decimal`
- `at: datetime`

本 change 不提供 OrderSink 具體實作；後續 `add-order-execution` 提供。

#### Scenario: OrderSink 結構驗證

- **WHEN** 任一具體實作含 submit 簽名
- **THEN** isinstance(impl, OrderSink) SHALL 回 True

#### Scenario: Fill 不可變

- **WHEN** 嘗試修改 Fill 任一欄位
- **THEN** SHALL 拋 FrozenInstanceError

#### Scenario: Fill 可序列化

- **WHEN** 對 Fill 呼叫 to_dict() 並 json.dumps
- **THEN** SHALL 完整序列化（Decimal/UUID/datetime 正規化）
