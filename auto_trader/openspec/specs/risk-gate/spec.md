# risk-gate Specification

## Purpose
TBD - created by archiving change add-risk-gate. Update Purpose after archive.
## Requirements
### Requirement: 系統狀態機維護全系統風險狀態

風控閘 SHALL 在任意時刻維持以下六個狀態之一：`NORMAL`、`WARNING`、`THROTTLED`、`HALTED`、`KILL_SWITCH`、`MAINTENANCE`。系統啟動時 SHALL 從持久化儲存讀回上次狀態（若不存在則為 `NORMAL`），並在啟動後立即執行一次轉換評估，不等待週期 tick。

#### Scenario: 服務首次啟動使用預設狀態

- **WHEN** 系統首次啟動且無持久化狀態
- **THEN** 風控閘狀態為 `NORMAL`
- **AND** 啟動後 1 秒內執行第一次 tick 評估

#### Scenario: 服務重啟讀回先前狀態

- **WHEN** 系統重啟且持久化儲存中記錄為 `THROTTLED`
- **THEN** 風控閘啟動後狀態為 `THROTTLED`
- **AND** 啟動後立即執行 tick，依當下指標決定是否轉換

#### Scenario: 不可越級回升

- **WHEN** 風控閘當前為 `HALTED` 且 PnL 已回正
- **THEN** 狀態保持 `HALTED`，不自動降為 `THROTTLED` 或更輕

---

### Requirement: 系統狀態轉換依凍結閾值自動觸發

風控閘 SHALL 每 60 秒執行一次 tick，依日內 PnL 比例（佔總權益）與 API 錯誤率自動觸發狀態轉換。觸發閾值定義於 `config/risk.yaml`，可在啟動時調整。

預設轉換邏輯（自動方向，僅向下）：

- 日內 PnL < -7% → `KILL_SWITCH`（任何狀態皆可）
- 日內 PnL < -5% → `HALTED`
- 日內 PnL < -3% 或 API 錯誤率 > 5% → `THROTTLED`
- 日內 PnL < -2% → `WARNING`

向上自動回升僅限 `WARNING → NORMAL` 與 `THROTTLED → WARNING`，且需所有觸發條件解除。`HALTED` 與 `KILL_SWITCH` 不自動回升。

#### Scenario: PnL 跌破 -2% 進入 WARNING

- **WHEN** 風控閘當前為 `NORMAL` 且日內 PnL 為 -2.3%
- **THEN** 下一次 tick 後狀態變為 `WARNING`
- **AND** 發布 `StateChanged` 事件，附帶 `from=NORMAL, to=WARNING, reason="daily_pnl=-2.3%"`

#### Scenario: PnL 跌破 -5% 直接進入 HALTED

- **WHEN** 風控閘當前為 `WARNING` 且日內 PnL 突降至 -5.5%
- **THEN** 下一次 tick 後狀態跳過 `THROTTLED` 直接變為 `HALTED`

#### Scenario: WARNING 條件解除自動回升 NORMAL

- **WHEN** 風控閘當前為 `WARNING` 且日內 PnL 已回正至 0.5%
- **THEN** 下一次 tick 後狀態變為 `NORMAL`

#### Scenario: HALTED 不自動回升

- **WHEN** 風控閘當前為 `HALTED` 且 PnL 已回正
- **THEN** 狀態保持 `HALTED`，不自動降級

---

### Requirement: HALTED 與 KILL_SWITCH 必須人工解鎖

風控閘進入 `HALTED` 後 SHALL 拒絕任何自動回升，僅接受人工 reset 指令。風控閘進入 `KILL_SWITCH` 後 SHALL 立即發布 `EmergencyFlattenRequested` 事件，並強制 4 小時冷靜期；冷靜期內任何 reset 指令 SHALL 被拒絕。

#### Scenario: HALTED 接受人工 reset

- **WHEN** 風控閘為 `HALTED` 且收到操作員 `reset(target=NORMAL)` 指令
- **THEN** 狀態變為 `NORMAL`
- **AND** 發布 `StateChanged` 事件，`reason="manual_reset"`

#### Scenario: KILL_SWITCH 觸發自動全平請求

- **WHEN** 風控閘從任何狀態進入 `KILL_SWITCH`
- **THEN** 風控閘 SHALL 發布 `EmergencyFlattenRequested` 事件供下游 capability 消費
- **AND** 拒絕所有後續 OrderIntent

#### Scenario: KILL_SWITCH 冷靜期內拒絕 reset

- **WHEN** 風控閘在 14:00 進入 `KILL_SWITCH`，且操作員於 16:00 發送 reset 指令
- **THEN** reset 指令被拒絕，狀態保持 `KILL_SWITCH`
- **AND** 系統回應冷靜期剩餘時間（約 2 小時）

#### Scenario: KILL_SWITCH 冷靜期後接受 reset

- **WHEN** 風控閘進入 `KILL_SWITCH` 已超過 4 小時且操作員發送 reset 指令
- **THEN** 狀態變為 `NORMAL`

---

### Requirement: MAINTENANCE 狀態為人工專用且阻擋所有交易

`MAINTENANCE` 狀態 SHALL 僅由人工指令進入或離開。在 `MAINTENANCE` 期間，風控閘 SHALL 拒絕所有 OrderIntent，但 SHALL 不觸發自動全平。

#### Scenario: 人工進入維護模式

- **WHEN** 操作員發送 `enter_maintenance()` 指令
- **THEN** 狀態變為 `MAINTENANCE`，無視當前 PnL 或自動轉換邏輯

#### Scenario: 維護期間拒絕 OrderIntent

- **WHEN** 風控閘為 `MAINTENANCE` 且收到 OrderIntent
- **THEN** 回傳 `Decision(verdict=REJECT, reasons=[system_state=MAINTENANCE])`

---

### Requirement: 規則引擎採短路評估

`RuleEngine` SHALL 依註冊順序評估規則。規則分兩類：reject 類與 clamp 類。任一 reject 類規則回傳 REJECT 時，後續規則 SHALL 不再評估。Clamp 類規則 SHALL 累積套用，且 size 必須單調遞減。最後一步為原子資金預留。

註冊順序由 `RuleEngine` 建構時注入的 list 決定，`config/risk.yaml` 控制啟用清單，無自動發現機制。

#### Scenario: Reject 規則短路

- **WHEN** OrderIntent 流經三條規則 A（reject）、B（clamp）、C（clamp），且 A 回傳 REJECT
- **THEN** B 與 C 不被評估
- **AND** Decision 的 `reasons` 僅包含 A 的 RuleVerdict

#### Scenario: Clamp 規則累積收斂

- **WHEN** OrderIntent qty=10，依序通過 PerOrderSizeCap（限 8）、StrategyBudgetCap（限 6）、SymbolConcentrationCap（限 5）
- **THEN** 最終 Decision.final_size = 5
- **AND** `reasons` 列出三條規則的 RuleVerdict（每條的 before/after 值）

#### Scenario: Clamp 規則違反單調遞減為 bug

- **WHEN** 某 clamp 規則回傳的 final_size 大於入參 size
- **THEN** RuleEngine 在 debug 模式 SHALL 拋出例外
- **AND** 在 production 模式 SHALL 記錄錯誤並忽略該規則的修正值

---

### Requirement: Decision 與 RuleVerdict 為不可變值物件

每筆 OrderIntent 經風控閘 SHALL 產生唯一一個 `Decision`。`Decision` 與其包含的 `RuleVerdict` 列表 SHALL 為不可變物件（frozen dataclass），可序列化為 JSON 供審計。

`Decision` 結構：

- `verdict`: `APPROVE` | `REJECT` | `DEFER`
- `final_size`: Decimal
- `final_price`: Optional[Decimal]
- `reasons`: list[RuleVerdict]
- `reservation_id`: Optional[UUID]（僅 APPROVE 時非空）
- `evaluated_at`: datetime（來自注入的 Clock）

`RuleVerdict` 結構：

- `rule_name`: str
- `outcome`: `PASS` | `CLAMP` | `REJECT`
- `before_value`: Optional[Decimal]
- `after_value`: Optional[Decimal]
- `message`: str
- `metadata`: dict[str, Any]（彈性擴充欄位）

#### Scenario: Decision 序列化

- **WHEN** 任一 Decision 物件呼叫 `dataclasses.asdict()`
- **THEN** 輸出為純資料 dict，不含函式或不可序列化型別
- **AND** dict 可透過 `json.dumps()` 完整序列化（Decimal 以 string 表達）

#### Scenario: Decision 不可變

- **WHEN** 嘗試修改 Decision 任一欄位
- **THEN** 拋出 `dataclasses.FrozenInstanceError`

---

### Requirement: SystemStateRule 依 FSM 狀態決定門檻

`SystemStateRule` SHALL 訂閱 `EventPublisher` 的 `StateChanged` 事件，於記憶體中快取最新 FSM 狀態。對每筆 OrderIntent，其行為依 FSM 狀態：

- `NORMAL` / `WARNING` → PASS（不修改）
- `THROTTLED` → CLAMP，將 final_size 乘以 0.5
- `HALTED` / `KILL_SWITCH` / `MAINTENANCE` → REJECT

啟動時 SHALL 主動同步查詢 FSM 取得初始狀態，不等首次事件。

#### Scenario: NORMAL 狀態通過

- **WHEN** FSM 為 `NORMAL` 且收到 OrderIntent qty=10
- **THEN** SystemStateRule 回傳 RuleVerdict(outcome=PASS, before=10, after=10)

#### Scenario: THROTTLED 狀態縮量 50%

- **WHEN** FSM 為 `THROTTLED` 且收到 OrderIntent qty=10
- **THEN** SystemStateRule 回傳 RuleVerdict(outcome=CLAMP, before=10, after=5)

#### Scenario: HALTED 狀態拒絕

- **WHEN** FSM 為 `HALTED` 且收到 OrderIntent
- **THEN** SystemStateRule 回傳 RuleVerdict(outcome=REJECT, message 含 "system_state=HALTED")

---

### Requirement: IdempotencyRule 以 signal_id 為主鍵 5 分鐘 TTL 去重

`IdempotencyRule` SHALL 維護一個以 `signal_id` 為主鍵的快取，TTL 為 5 分鐘（可由 `config/risk.yaml` 覆寫）。同一 `signal_id` 在 TTL 內第二次出現 SHALL 被 REJECT。

實作 SHALL 提供記憶體上限（預設 100,000 筆）與 LRU 淘汰策略，避免無限成長。

#### Scenario: 首次出現的 signal_id 通過

- **WHEN** OrderIntent 帶 signal_id="abc123" 首次到達
- **THEN** IdempotencyRule 回傳 RuleVerdict(outcome=PASS)
- **AND** "abc123" 寫入快取，TTL 5 分鐘

#### Scenario: 5 分鐘內重送被拒絕

- **WHEN** signal_id="abc123" 已在快取中（30 秒前）且再次到達
- **THEN** IdempotencyRule 回傳 RuleVerdict(outcome=REJECT, message="duplicate signal_id within TTL")

#### Scenario: 5 分鐘後重送視為新訊號

- **WHEN** signal_id="abc123" 上次出現於 6 分鐘前（已過 TTL）且再次到達
- **THEN** IdempotencyRule 回傳 RuleVerdict(outcome=PASS)
- **AND** "abc123" 重新寫入快取

#### Scenario: 快取達上限觸發 LRU 淘汰

- **WHEN** 快取已達上限 100,000 筆且新 signal_id 到達
- **THEN** 最久未使用的條目被淘汰
- **AND** 新 signal_id 寫入快取

---

### Requirement: CapitalReserver 為單一 actor 序列化處理預留

`CapitalReserver` SHALL 透過單一 `asyncio.Queue` 序列化所有預留請求，內部單一 worker 處理，保證 FCFS 順序。對外 API 為 `async reserve(intent) -> ReservationResult` 與 `async release(reservation_id) -> None`。

`ReservationLedger` SHALL 同時追蹤：

- `total_equity` / `total_reserved` / `total_free`
- `per_strategy[strategy_id]`：`max_budget`、`reserved`、`available`
- `per_symbol[symbol]`：`max_concentration`、`reserved`、`available`

預留時 SHALL 同時檢查三道：策略可用額度、標的集中度上限、全池可用。任一不足即拒絕並回傳具體不足項。

#### Scenario: 三道檢查全通過則成功預留

- **WHEN** Strategy A 請求預留 1000，且 strategy A available=2000、symbol BTC available=1500、global free=3000
- **THEN** 預留成功，回傳 `reservation_id`
- **AND** ledger 變為 strategy A reserved+=1000、symbol BTC reserved+=1000、total_reserved+=1000

#### Scenario: 任一檢查不足則拒絕

- **WHEN** Strategy A 請求預留 1000，但 symbol BTC available=500
- **THEN** 預留失敗，回傳 `ReservationResult(ok=False, reason="symbol_concentration_insufficient", available=500)`
- **AND** ledger 不變

#### Scenario: FCFS 順序保證

- **WHEN** 兩個並發請求 Req-A 與 Req-B，Req-A 在 Req-B 之前 1ms 進入 queue，且兩者都會耗盡剩餘額度
- **THEN** Req-A 預留成功、Req-B 預留失敗
- **AND** 不可能 Req-B 成功而 Req-A 失敗

#### Scenario: 釋放預留歸還額度

- **WHEN** 持有 reservation_id 的呼叫者呼叫 `release(reservation_id)`
- **THEN** 該筆預留額度歸還至 strategy/symbol/global 三道
- **AND** ledger 變更廣播 `ReservationReleased` 事件

#### Scenario: 重複釋放冪等

- **WHEN** 對同一 reservation_id 呼叫 `release` 兩次
- **THEN** 第一次成功，第二次 SHALL no-op（不拋例外、不重複歸還）

---

### Requirement: 風控閘僅依賴 ports 介面與下游互動

風控閘 SHALL 不直接依賴任何具體 Adapter（交易所 SDK、訊號來源、持久化實作）。所有外部互動透過 `risk/ports.py` 定義的 Protocol：

- `PositionReader`：`get_position(strategy_id, symbol) -> Position`、`list_positions() -> list[Position]`（read-only）
- `MarketDataReader`：`get_last_price(symbol) -> Decimal`（read-only）
- `ConfigReader`：`get(key: str) -> Any`（讀取最新配置）
- `EventPublisher`：`publish(event: Event) -> None`（write-only）

#### Scenario: 注入測試替身可獨立驗證 RuleEngine

- **WHEN** 測試以 mock `PositionReader` 與 mock `EventPublisher` 建構 RuleEngine
- **THEN** RuleEngine 可在無真實交易所、無真實事件總線的情況下完整運作

#### Scenario: 違反 ISP 應被測試攔截

- **WHEN** 任一規則嘗試呼叫 `PositionReader` 上不存在的方法（例如寫入）
- **THEN** Protocol 不暴露該方法，型別檢查（mypy）SHALL 阻擋
- **AND** 規則違反 read-only 假設視為 bug

---

### Requirement: 配置以 YAML 表達且啟動時驗證

`config/risk.yaml` SHALL 使用 pydantic 模型驗證。驗證失敗 SHALL 阻止啟動，並回報具體錯誤位置。配置變更 SHALL 在重啟後生效，本 change 不支援熱載入。

配置必含區段：

- `fsm.thresholds`：FSM 觸發 PnL %、API 錯誤率、冷靜期長度
- `rules.enabled`：啟用的規則名稱列表（決定執行順序）
- `rules.params`：每條規則的參數（如 IdempotencyRule TTL、PerOrderSizeCap 上限）
- `clock.tz`：跨日 P&L 重置時區（預設 `UTC`）

#### Scenario: 啟動時配置驗證成功

- **WHEN** `config/risk.yaml` 內容符合 pydantic schema
- **THEN** 風控閘正常啟動
- **AND** 啟動日誌包含 `params_hash`（配置內容 SHA-256）

#### Scenario: 配置缺欄位阻止啟動

- **WHEN** `config/risk.yaml` 缺少 `fsm.thresholds.daily_pnl_kill`
- **THEN** 啟動失敗，標準錯誤輸出包含具體缺失欄位路徑

#### Scenario: 配置型別錯誤阻止啟動

- **WHEN** `config/risk.yaml` 中 `fsm.thresholds.daily_pnl_kill` 為字串而非數字
- **THEN** 啟動失敗，錯誤訊息指出型別不符

---

### Requirement: 所有時間相依邏輯透過 Clock Protocol 注入

風控閘所有需要當前時間的邏輯（FSM tick 排程、IdempotencyRule TTL、訊號 freshness、跨日 P&L 重置、KILL_SWITCH 冷靜期計時）SHALL 透過注入的 `Clock` Protocol 取得時間，禁止直接呼叫 `datetime.now()` 或 `time.time()`。

`Clock` Protocol 暴露：

- `now() -> datetime`：當前 wall-clock 時間（含 tz）
- `monotonic() -> float`：單調遞增秒數（用於 timer）

#### Scenario: 注入測試 Clock 可控制時間流

- **WHEN** 測試注入 `FrozenClock(initial=2026-05-10T00:00:00Z)`
- **THEN** 所有風控閘元件視當前時間為該固定值
- **AND** 測試呼叫 `clock.advance(timedelta(minutes=6))` 可前進時間，觀察 IdempotencyRule TTL 過期行為

#### Scenario: 跨日重置依配置時區

- **WHEN** `config.clock.tz = UTC` 且當前時間從 23:59:59 變為 00:00:00 UTC
- **THEN** 日內 P&L 計數器重置
- **AND** 發布 `DailyPnlReset` 事件

---

### Requirement: 所有風控決策與狀態變更須發布事件供審計

風控閘 SHALL 在以下時機發布事件至 `EventPublisher`：

- FSM 狀態變更：`StateChanged(from, to, reason, at)`
- KILL_SWITCH 觸發：`EmergencyFlattenRequested(at)`
- 每筆 Decision：`DecisionEmitted(decision)`
- Reservation 變化：`ReservationCreated(reservation_id)`、`ReservationReleased(reservation_id)`
- 配置載入：`ConfigLoaded(params_hash, at)`
- 跨日重置：`DailyPnlReset(at)`

事件 SHALL 為不可變值物件，附帶 `event_id` (UUID) 與 `at` (datetime)。

#### Scenario: 每筆 Decision 觸發一個事件

- **WHEN** RuleEngine 對某 OrderIntent 產生 Decision
- **THEN** EventPublisher 收到一筆 `DecisionEmitted` 事件
- **AND** 事件附帶完整 Decision 物件

#### Scenario: KILL_SWITCH 同時觸發兩個事件

- **WHEN** FSM 從 `HALTED` 進入 `KILL_SWITCH`
- **THEN** EventPublisher 依序收到 `StateChanged(from=HALTED, to=KILL_SWITCH)` 與 `EmergencyFlattenRequested`

#### Scenario: 事件可序列化供 SQLite event log

- **WHEN** 任一事件呼叫 `to_dict()` 並寫入 JSON
- **THEN** 結果為純資料、可被後續 capability 寫入 SQLite，無資訊遺失

---

### Requirement: 啟動時暖機 30 秒不接受 OrderIntent

風控閘啟動完成後 SHALL 進入 30 秒暖機期，期間：

- FSM 立即執行首次 tick（不等 60 秒）
- IdempotencyRule、CapitalReserver、StateStore 完成記憶體結構初始化
- 暖機期間收到的 OrderIntent SHALL 被 REJECT 並附理由 `system_warming_up`

暖機期長度 SHALL 可由 `config/risk.yaml` 覆寫。

#### Scenario: 暖機期內拒絕 OrderIntent

- **WHEN** 服務啟動 10 秒後收到 OrderIntent
- **THEN** Decision verdict=REJECT，reasons 包含 `system_warming_up`

#### Scenario: 暖機期結束後正常處理

- **WHEN** 服務啟動 31 秒後收到 OrderIntent
- **THEN** OrderIntent 進入正常 RuleEngine 評估流程

### Requirement: SignalFreshnessRule 拒絕過舊訊號

`SignalFreshnessRule` SHALL 比較 `ctx.intent.bar_time` 與 `ctx.clock.now()` 的差距；超過 `max_age_seconds`（預設 30）SHALL 回 REJECT。

#### Scenario: 訊號在閾值內通過

- **WHEN** intent.bar_time 與 now() 相差 10 秒，max_age_seconds=30
- **THEN** SHALL 回 PASS

#### Scenario: 訊號超過閾值拒絕

- **WHEN** intent.bar_time 與 now() 相差 60 秒，max_age_seconds=30
- **THEN** SHALL 回 REJECT，message 含 age 與 threshold

---

### Requirement: SymbolWhitelistRule 限制可交易標的

`SymbolWhitelistRule` SHALL 依配置 `symbols: list[str]` 行為：

- 空清單：接受所有 symbol（PASS）
- 非空清單：僅接受清單內 symbol，否則 REJECT

#### Scenario: 空白名單接受全部

- **WHEN** symbols=[] 且 intent.symbol="BTCUSDT"
- **THEN** SHALL 回 PASS

#### Scenario: 在白名單通過

- **WHEN** symbols=["BTCUSDT","ETHUSDT"] 且 intent.symbol="BTCUSDT"
- **THEN** SHALL 回 PASS

#### Scenario: 不在白名單拒絕

- **WHEN** symbols=["BTCUSDT"] 且 intent.symbol="SOLUSDT"
- **THEN** SHALL 回 REJECT

---

### Requirement: StrategyPausedRule 拒絕非 ACTIVE 策略訊號

`StrategyPausedRule` SHALL 透過 `StrategyStateReader.get_state(strategy_id)` 查策略狀態：非 ACTIVE 即 REJECT；reader 找不到（None）也 REJECT。

#### Scenario: ACTIVE 通過

- **WHEN** state="ACTIVE"
- **THEN** SHALL 回 PASS

#### Scenario: PAUSED 拒絕

- **WHEN** state="PAUSED"
- **THEN** SHALL 回 REJECT

#### Scenario: 未知 strategy_id 拒絕

- **WHEN** reader.get_state 回 None
- **THEN** SHALL 回 REJECT

---

### Requirement: PerOrderSizeCap 限制單筆訂單佔總權益

`PerOrderSizeCap` SHALL 依配置 `max_pct_of_equity`（預設 0.05）與注入的 `EquityReader` 計算上限：

```
notional_cap = max_pct_of_equity × equity
qty_cap = notional_cap / price
clamped = min(current_size, qty_cap)
```

`price` 為 intent.price；intent.price 為 None 時使用 `market_data.get_last_price(symbol)`。

#### Scenario: 超過上限 CLAMP

- **WHEN** current_size=1000，equity=10000，max_pct=0.05，price=1（cap = 500 qty）
- **THEN** SHALL 回 CLAMP，after_value=500

#### Scenario: 在上限內 PASS

- **WHEN** current_size=100，equity=10000，max_pct=0.05，price=1（cap = 500）
- **THEN** SHALL 回 PASS

---

### Requirement: StrategyBudgetCap 限制策略累積金額

`StrategyBudgetCap` SHALL 依注入的 `ReservationLedgerReader.strategy_available(strategy_id)` 計算 max_qty 並 clamp。

#### Scenario: 策略額度不足 CLAMP

- **WHEN** strategy_available=500，price=10（max_qty=50），current_size=100
- **THEN** SHALL 回 CLAMP，after_value=50

---

### Requirement: SymbolConcentrationCap 限制單一標的曝險

`SymbolConcentrationCap` SHALL 依注入的 `ReservationLedgerReader.symbol_available(symbol)` 計算 max_qty 並 clamp。

#### Scenario: 標的集中度不足 CLAMP

- **WHEN** symbol_available=300，price=10（max_qty=30），current_size=100
- **THEN** SHALL 回 CLAMP，after_value=30

---

### Requirement: ThrottleScaler 預設 no-op

`ThrottleScaler` SHALL 預設 PASS（不修改 size）。配置 `scaler` < 1.0 且 FSM 為 THROTTLED 時可主動 CLAMP；MVP 保留為 no-op。

#### Scenario: 預設配置下 PASS

- **WHEN** scaler 預設值
- **THEN** SHALL 回 PASS，size 不變

---

### Requirement: PriceSanityCheck 拒絕偏離 last 過大的限價單

`PriceSanityCheck` SHALL 比對 intent.price 與 `market_data.get_last_price(symbol)`：

- intent.price 為 None（市價單）→ PASS
- abs(price - last) / last > max_deviation_pct（預設 0.05） → REJECT

#### Scenario: 市價單 PASS

- **WHEN** intent.price=None
- **THEN** SHALL 回 PASS

#### Scenario: 限價偏離合理範圍 PASS

- **WHEN** intent.price=65000, last=65500（偏離 0.76%），max=5%
- **THEN** SHALL 回 PASS

#### Scenario: 限價偏離過大 REJECT

- **WHEN** intent.price=70000, last=65000（偏離 7.7%），max=5%
- **THEN** SHALL 回 REJECT

---

### Requirement: CapitalReservationRule 預留資金並注入 reservation_id

`CapitalReservationRule` SHALL 透過注入的 `CapitalReserver`：

1. 計算 notional = current_size × (intent.price 或 market_data.last_price)
2. 呼叫 `await reserver.reserve(intent, notional)`
3. 成功 → PASS，metadata 含 `reservation_id` 字串
4. 失敗（ledger 三道任一不足）→ REJECT，message 含 reason

`RuleEngine` SHALL 在組 Decision 時，自最後一條 RuleVerdict.metadata 中抽 `reservation_id` 寫入 `Decision.reservation_id`（若存在）。

#### Scenario: 預留成功 metadata 含 reservation_id

- **WHEN** reserver.reserve 成功
- **THEN** RuleVerdict.outcome=PASS，metadata["reservation_id"] 為 UUID 字串

#### Scenario: 預留失敗 REJECT

- **WHEN** ledger 集中度不足
- **THEN** RuleVerdict.outcome=REJECT，message 含 reason

#### Scenario: Decision 抽 reservation_id

- **WHEN** 流程通過 CapitalReservationRule 並成功預留
- **THEN** Decision.reservation_id SHALL 與 metadata 中的值一致

