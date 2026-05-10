## Why

自動化交易系統的命脈是風險控制。沒有風控閘的下單服務等於裸奔，
任何單筆爆量、訊號重送、API 故障、策略 bug 都可能在短時間內把帳戶清零。
本專案的工程順序刻意把 risk-gate 列為**第一個建立的 capability**，理由有三：

1. 訊號入口、訂單執行、對帳等下游元件都需要呼叫風控閘的判決，介面要先凍結。
2. 風控政策的決策面最複雜（FSM 6 狀態 × 11 條規則 × 並發資金預留），先把契約定下來，
   後續 capability 才能在穩定的依賴上開發。
3. 風控錯了會造成實質金錢損失；其他元件錯了大多只是不便。風險越大、越要先做。

延伸：`docs/design-brief.md` 第 6 節（風控閘設計）、第 4 節（凍結決策）、第 8 節（SOLID 落點）。

## What Changes

- **新增** `risk-gate` capability，提供雙層風險控制：
  - **Layer 1 系統狀態機（FSM）**：6 個全系統狀態
    - `NORMAL` / `WARNING` / `THROTTLED` / `HALTED` / `KILL_SWITCH` / `MAINTENANCE`
    - 每 60 秒 tick 一次，依日內 PnL、API 健康度、操作員指令計算狀態轉換
    - `HALTED` 必須人工解鎖（D1）；`KILL_SWITCH` 觸發後自動全平 + 4 小時冷靜期（D2）
  - **Layer 2 RuleEngine**：可插拔規則 pipeline
    - 短路評估（D3）：先過 reject 類規則，再過 clamp 類規則，最後原子資金預留
    - 11 條規則僅定義契約（Protocol），本 change 只實作 `SystemStateRule` 與 `IdempotencyRule` 兩條示範
    - Decision 物件帶 `reasons: list[RuleVerdict]`，全程審計可追溯

- **新增** `CapitalReserver` actor（D5）
  - 單一 asyncio queue 序列化資金預留請求，解決多策略並發競爭
  - 維護 `ReservationLedger`：per-strategy budget、per-symbol concentration、global free
  - FCFS 先到先得（死角備案凍結項）

- **新增** `ports.py` DIP 邊界
  - `PositionReader` / `MarketDataReader` / `ConfigReader` / `EventPublisher` 四個 Protocol
  - RuleEngine、StateMachine 只依賴 Protocol，不認識具體 Adapter
  - 為後續 capability（`strategy-host`、`order-execution`、`reconciliation`）提供穩定整合點

- **新增** `config/risk.yaml`（D4）
  - FSM 觸發閾值（PnL %、API error rate、冷靜期長度）
  - 11 條規則的參數（per-order cap、concentration cap、freshness TTL 等）
  - 5 分鐘 signal_id 去重 TTL（D6）為硬編碼預設、可由 YAML 覆寫

- **訊號去重契約**（D6）：`IdempotencyRule` 以 `signal_id` 為主鍵維護 5 分鐘 TTL 快取，
  重送即拒絕（不視為 update）。

- **多策略並行政策落點**（E1–E7）：
  - E1 共池 + 軟上限：在 `ReservationLedger` 體現
  - E5 Naive 路由：本 capability 不主動淨化訂單（保留給 `order-execution`）
  - 其他項在 RuleEngine 規則中體現（E6 backpressure 屬 `signal-ingestion`，本 change 不含）

### 範圍外（留給後續 change）

- 另 9 條規則的具體實作（freshness、whitelist、concentration、price sanity 等）
- SQLite event log persistence（本 change 為 in-memory + 啟動讀回介面）
- Telegram/Email 告警（屬 `observability` capability）
- 與 `strategy-host` / `order-execution` / `reconciliation` 的實際整合
- HFT 級的樂觀鎖預留優化

## Capabilities

### New Capabilities

- `risk-gate`：系統級風險控制核心。提供
  - 系統狀態機（FSM）的狀態管理與自動轉換
  - 可插拔 RiskRule 規則引擎（短路評估）
  - 原子資金預留（actor pattern）
  - 對外 DIP 介面（PositionReader / MarketDataReader / ConfigReader / EventPublisher）

### Modified Capabilities

無。本 change 為專案第一個 spec。

## Impact

### 程式碼結構（新增）

```
risk/
├── state/                  系統狀態機（Layer 1）
│   ├── machine.py          StateMachine 引擎
│   ├── transitions.py      TransitionPolicy（純規則函式）
│   └── persistence.py      StateStore（介面，in-memory 實作）
├── rules/                  Layer 2 規則
│   ├── base.py             RiskRule Protocol、Decision、RuleVerdict
│   ├── system_state.py     SystemStateRule（本 change 實作）
│   ├── idempotency.py      IdempotencyRule（本 change 實作）
│   └── _stubs.py           另 9 條規則的契約 stub（NotImplementedError）
├── reservation/
│   ├── reserver.py         CapitalReserver actor
│   └── ledger.py           ReservationLedger 值物件
├── engine.py               RuleEngine 編排器
└── ports.py                DIP 邊界 Protocol 集
```

### 配置

- 新增 `config/risk.yaml`：FSM 閾值 + 11 條規則參數

### 依賴

- 無新外部依賴（Python 3.11+、`asyncio`、`pydantic` 已在專案默認技術棧）
- SQLite 等持久化方案留給後續 change

### 對未來 capability 的契約承諾

- `signal-ingestion` 將消費 `IdempotencyRule` 的去重邏輯（共用 TTL 快取或介面）
- `strategy-host` 將呼叫 `RuleEngine.evaluate(intent)` 取得 `Decision`
- `order-execution` 將執行 `APPROVE` 後的訂單，並回傳 `reservation_id` 供釋放
- `reconciliation` 將透過 `EventPublisher` 訂閱 fill 事件，更新 ledger 與 logical book
- `observability` 將透過 `EventPublisher` 訂閱所有風控事件供告警與審計

### 風險與權衡

- **In-memory 狀態**：服務重啟會喪失 FSM 狀態與訊號去重快取，
  本 change 提供讀回介面但實作為 no-op，後續 change 補上 SQLite persistence
- **規則契約凍結成本**：11 條規則的入參出參簽名一旦發布，後續修改成本高；
  此 change 必須謹慎設計 Protocol，預留擴充欄位
- **單 actor 並發瓶頸**：CapitalReserver 設計為單一序列化處理；
  MVP 預估每秒幾十筆訊號內可接受，HFT 場景需後續優化（不在本專案範圍）
