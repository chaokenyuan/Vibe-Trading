## Context

`risk-gate` 是 vibe-auto-trader 的第一個 capability，亦是整個系統的命脈。它必須在訊號進入訂單執行前作為**唯一的決策關卡**，吸收所有「該不該下這筆單」的判斷邏輯。

當前狀態：

- 專案剛起步，僅有 README/LICENSE/.gitignore 與 `docs/design-brief.md` 探索成果
- 全系統尚未實作任何 capability，本 change 將定下後續 5 個 capability 的整合契約
- 凍結決策已涵蓋宏觀風險政策（D1–D6、E1–E7、死角備案），本文件聚焦在「如何把政策落到 OO 結構」

關鍵約束：

- **Python 3.11+，asyncio 單進程**：簡化並發模型、便於除錯，犧牲水平擴展（個人自用可接受）
- **MVP 不上 SQLite**：所有狀態 in-memory；服務重啟意味重建（讀回介面預留）
- **延遲容忍**：每筆訊號秒級判決可接受；不需要無鎖資料結構
- **多策略並行**：寫者單例（FSM、RuleEngine、CapitalReserver、OrderExecutor、Reconciler），讀者無上限

利害關係人：

- **使用者**：個人自用，需要可信任的硬閘煞車
- **下游 capability 開發者（即未來的我）**：`ports.py` 是與其他 capability 接觸的唯一介面，介面凍結品質直接決定整體開發效率
- **稽核視角**：每一筆 Decision 必須能 100% 回放，符合「回測再現性」的工程承諾

## Goals / Non-Goals

### Goals

1. 把雙層風控（FSM + Rule pipeline）落為兩個完全解耦的子模組，允許獨立測試與替換
2. 凍結 11 條規則的 Protocol 契約（簽名 + 入參出參 + 錯誤模型），未來實作不需修改 RuleEngine
3. 提供 `CapitalReserver` actor 作為唯一的資金真相來源，杜絕跨策略 race condition
4. `ports.py` 切細介面（ISP），與其他 capability 的整合點明確且最小
5. 所有時間相依邏輯（FSM tick、訊號 freshness、TTL）透過注入的 `Clock` 抽象，可測試
6. 任一 Decision 必須帶完整 `RuleVerdict` 軌跡，可序列化、可審計、可重放

### Non-Goals

1. 不解決訊號進入前的問題（webhook 認證、payload 解析屬 `signal-ingestion`）
2. 不解決訂單實際送出（屬 `order-execution`），本 change 只產出 `Decision`
3. 不解決持倉對帳（屬 `reconciliation`）
4. 不提供 SQLite 持久化（後續 change）
5. 不提供 Telegram/Email 告警通道（屬 `observability`，但本 change 提供 `EventPublisher` 介面）
6. 不提供熱載入規則（重啟才換，與 E3 凍結一致）
7. 不提供樂觀鎖／無鎖資金預留（actor 序列化已足，不過度工程）

## Decisions

### D-1：雙層分離（FSM 與 RuleEngine 兩個獨立子模組）

**決策**：Layer 1（系統 FSM，慢變數）與 Layer 2（單筆訂單規則 pipeline，快變數）放兩個目錄，不共用程式路徑，僅透過 `SystemStateRule` 把 FSM 結果引入 Rule pipeline。

**替代方案**：

- 一個大型 `evaluate(intent)` 把所有判斷攤平：邏輯一坨、難以單獨測試 FSM、難以分別演化
- FSM 內部呼叫 RuleEngine：循環依賴、邊界模糊

**理由**：

- FSM 跟 RuleEngine 的觸發頻率、輸入、生命週期完全不同（每分鐘 vs 每筆、PnL/API 健康度 vs 訂單意圖）
- 分離後，FSM 政策可以獨立演化（例如未來加 ML 異常偵測）而不動 RuleEngine
- 符合 SRP

### D-2：FSM 採 6 狀態而非更精簡

**決策**：6 狀態（NORMAL / WARNING / THROTTLED / HALTED / KILL_SWITCH / MAINTENANCE）。

**替代方案**：

- 3 狀態（NORMAL / DEGRADED / STOPPED）：太粗，無法表達「告警繼續交易」與「縮量交易」的差異
- 連續分數（risk_score 0–1）：難以審計、難以對使用者解釋當前狀態

**理由**：

- WARNING 與 THROTTLED 是有意義的「過渡層」，給操作員充足反應時間
- KILL_SWITCH 必須是獨立狀態（單向閥 + 4h 冷靜期），不能與 HALTED 混淆
- MAINTENANCE 是人工強制狀態（升級/遷移），與其他自動狀態正交

### D-3：Rule Pipeline 採短路評估（D3 凍結）

**決策**：規則分兩段，先過 reject 類（任一拒則終止），再過 clamp 類（累積 size 修正），最後原子預留。

**替代方案**：

- 全部規則都跑（收集所有 reasons 再判決）：理論上資訊完整但成本高、且 reject 後再算 clamp 無意義
- 規則任意排序：clamp 類可能放在 reject 類之前白做工

**理由**：

- 性能：reject 短路省掉昂貴的 clamp 計算
- 邏輯：reject 後 size 不再有意義，clamp 是浪費
- 可預測性：開發者能依序推理「會先過哪些檢查」

**取捨**：被 reject 的訊號只會記錄到第一個 reject 規則的 reason，後續規則不評估。如果未來需要「列出所有違反項」用於 UI 提示，需另開「dry-run」模式。

### D-4：Decision 與 RuleVerdict 為不可變值物件（frozen dataclass）

**決策**：所有 Decision、RuleVerdict 為 `frozen=True` dataclass，可序列化（`dataclasses.asdict`）為 audit log。

**替代方案**：

- `dict` 自由結構：型別不安全、易拼錯欄位
- pydantic BaseModel：較重，本層不需要驗證（驗證在 ports 邊界）

**理由**：

- 不可變保證沒有後續竄改
- frozen dataclass 跟 protobuf/pydantic 比輕量，足以表達結構
- 序列化簡單，便於 SQLite event log（後續 change）

### D-5：CapitalReserver 採單一 actor（asyncio queue）

**決策**：CapitalReserver 包裝為 actor，所有預留請求進單一 `asyncio.Queue`，內部單執行緒處理。對外暴露 `async def reserve(intent) -> ReservationOrError`。

**替代方案**：

- `asyncio.Lock` 包住 ledger：可以但仍需序列化，actor 模型語意更明確
- 樂觀鎖 + 重試：MVP 過度工程
- DB transaction（SQLite IMMEDIATE）：MVP 階段不上 SQLite

**理由**：

- 序列化天然消除 race condition
- 單一寫者使邏輯易推理
- 後續若需要持久化，actor 內部換成 SQLite tx 對外契約不變
- FCFS 自然保證（queue 順序 = 處理順序）

### D-6：規則插件透過顯式註冊，不靠自動發現

**決策**：`RuleEngine` 接受 `list[RiskRule]` 在建構時注入；註冊順序即執行順序。`config/risk.yaml` 控制啟用哪些規則。

**替代方案**：

- 自動掃描 `risk/rules/` 目錄：簡潔但隱式，順序由檔名決定（脆弱）
- 裝飾器自動註冊：執行 import 副作用，難以測試

**理由**：

- 顯式 > 隱式（Zen of Python）
- 順序可控：reject 類先於 clamp 類，YAML 配置裡明確
- 測試可注入 mock rule，無需 monkey-patch

### D-7：時間透過 `Clock` 抽象注入

**決策**：所有時間相依邏輯（FSM tick 排程、TTL、訊號 freshness）依賴注入的 `Clock` Protocol，而非直接呼叫 `datetime.now()`。

**替代方案**：

- 直接 `datetime.now()`：測試需 monkey-patch `datetime`，脆弱
- `time.monotonic()`：適合 timer 但不適合 wall-clock 邏輯（如跨日 P&L UTC 0:00 重置）

**理由**：

- 可測試：測試 `freshness > 30s` 規則時注入固定時鐘
- 可審計：所有事件帶 `clock.now()` 的同一時間源
- 為未來「歷史回放」鋪路：注入歷史 clock 即可重跑

### D-8：YAML 配置使用 pydantic 驗證

**決策**：`config/risk.yaml` 解析後映射為 pydantic BaseModel；啟動時驗證、失敗則拒絕啟動。

**替代方案**：

- `dict` 直接用：型別不安全、預設值散落
- TOML：可讀性主觀差異、生態不如 YAML
- 程式碼即配置（Python file）：不符合 D4 凍結（配置應為資料）

**理由**：

- 配置錯誤越早爆越好（fail-fast）
- pydantic 自動產生 schema，方便寫 docs
- YAML 在運維生態最普遍

### D-9：錯誤模型 — Decision 為單一回傳，例外只用於 bug

**決策**：

- 規則違反（reject、clamp）→ 透過 `Decision`/`RuleVerdict` 表達，不丟例外
- 程式 bug、ports adapter 失敗 → 丟例外（讓上層 catch + 進 FAILED 流程）

**替代方案**：

- 全部例外：規則拒絕變成 control flow via exception，效能與可讀性差
- Result/Either monad：Python 生態不熟悉，引入成本高

**理由**：

- 規則違反是業務語意而非異常
- 例外成本高、流程混亂
- Decision 物件天然可審計

### D-10：FSM tick 與 RuleEngine 解耦透過 Event Bus

**決策**：FSM 狀態變遷透過 `EventPublisher` 廣播 `StateChanged` 事件；`SystemStateRule` 訂閱該事件並快取最新狀態，不直接呼叫 FSM。

**替代方案**：

- `SystemStateRule` 直接持有 FSM reference：耦合
- 共用 mutable global：全域狀態反模式

**理由**：

- DIP：Rule 只依賴 `EventPublisher` Protocol
- 事件流可被 `observability` 共用（一份廣播多份消費）
- 為未來「集群部署」鋪路（事件可發到 Redis pub/sub）

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| **R-1 規則 Protocol 凍結成本高**：11 條規則簽名一旦發布，未來欄位增刪會擴散 | Protocol 預留 `context: RuleContext` 包裝物件作為入參，新欄位加在 Context 內；輸出 `RuleVerdict` 預留 `metadata: dict[str, Any]` 作為彈性擴充點 |
| **R-2 In-memory 狀態重啟丟失**：FSM 狀態、訊號去重表、ledger 在重啟後喪失 | `StateStore` Protocol 預留，本 change 實作 `InMemoryStateStore`；後續 change 加 `SqliteStateStore`；重啟時所有 strategy 進入 30 秒暖機（已凍結） |
| **R-3 單 actor 序列化瓶頸**：CapitalReserver 單執行緒處理上限約幾百 req/s | MVP 個人帳戶量級遠低於此；超過再升級為樂觀鎖（介面不變） |
| **R-4 規則之間的隱性順序依賴**：clamp 類規則被互相影響時可能違反開發者直覺 | 在 RuleEngine 加 invariant 檢查（debug 模式）：clamp 後 size 必須單調遞減；違反則拋例外 |
| **R-5 時間 race**：FSM tick 跟訂單評估可能撞時序，導致剛降級的訂單已通過 | 接受。FSM 是慢變數，邊界訂單不大；`reasons` 記錄當下 FSM snapshot 供審計 |
| **R-6 Event bus 成順序依賴**：StateChanged 事件未到達 SystemStateRule 時，新訊號可能用舊 FSM 狀態判決 | `SystemStateRule` 啟動時主動查 FSM 取得初始狀態（單次同步呼叫），之後靠事件更新；事件丟失視為 bug |
| **R-7 YAML 配置漂移**：deployed config 與 spec 不同步 | 啟動時計算 `params_hash`，寫入啟動日誌；後續 change 在每筆 Decision 帶 `params_hash` 供審計 |
| **R-8 Mock rule 滲透到生產**：測試替身被誤裝載 | RuleEngine 建構接受顯式 list，無自動發現機制；`config/risk.yaml` 列出 production rule 清單，CI 測試比對 |
| **R-9 KILL_SWITCH 全平指令丟失**：FSM 進入 KILL_SWITCH 但全平動作未執行 | 本 change 不負責全平實作（屬 `order-execution`），但定義 `EmergencyFlattenRequested` 事件契約；`order-execution` 必須冪等消費並回報執行結果 |
| **R-10 冷啟動的 FSM 漏判**：重啟後 30 秒暖機期內若 PnL 已劇烈下跌，FSM 可能反應不及 | 接受。30 秒暖機是為了 LogicalBook 重建；FSM 啟動時應立即執行一次 tick（不等 60 秒週期） |

## Migration Plan

本 change 為新建，無既有狀態需遷移。部署步驟：

1. 建立 `risk/` 模組結構與檔案（依 proposal Impact 章節）
2. 建立 `config/risk.yaml` 預設值（FSM 閾值、11 規則參數）
3. 提供 `RiskGate.from_config(path)` factory 作為主要入口
4. 撰寫單元測試：FSM 6 狀態 × 轉換邊界 + RuleEngine 短路 + CapitalReserver 並發測
5. 整合測試：模擬 100 個並發 intent 確認 ledger 一致性
6. 後續 change 才會把 RiskGate 接到 strategy-host

回滾策略：本 change 為純新增，無修改既有檔案。回滾即刪除 `risk/` 與 `config/risk.yaml`。

## Open Questions

1. **FSM 的「自動降級」是否需要冷卻期**：例如 THROTTLED → WARNING 是否要等 PnL 穩定 N 分鐘才降，避免抖動？目前傾向「立刻降」（簡單），但若實測抖動嚴重再加 hysteresis。建議在 specs 階段以 scenario 表達兩種行為，留待後續決策。
2. **`CapitalReserver` 的 ledger 快照頻率**：對外是否提供 `snapshot()` 介面供 observability 取樣？頻率？建議在 spec 階段定義為「on-demand pull + 每筆變更 push event」雙模式。
3. **規則啟用清單變更如何審計**：YAML 改動只在重啟生效，但若部署過程改了卻沒重啟，會有無聲偏差。建議啟動時把當前 active rule 集合寫入啟動日誌，後續 change 加 health endpoint 暴露此資訊。
4. **`IdempotencyRule` 的 TTL 快取記憶體上限**：5 分鐘 TTL × 每秒 N 訊號 = 上限 300×N 筆。N=100 即 30k 筆 entries，記憶體可接受。但若超量需 LRU 截尾。建議 spec 中表達「實作必須有上限與淘汰策略」，具體數字延後。
5. **多策略對同一 strategy_id 的 collision**：兩個 strategy 不小心配同 `strategy_id` 會造成 ledger 與 logical book 錯亂。建議 `StrategyRegistry` 在啟動時驗證唯一性，但這屬於 `strategy-host` 範疇，本 change 在 ports 層只做 read-only 假設。
