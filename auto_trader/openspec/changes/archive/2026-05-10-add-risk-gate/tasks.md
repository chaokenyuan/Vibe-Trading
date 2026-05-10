## 1. 專案骨架與依賴

- [x] 1.1 建立 `risk/` 套件目錄與子模組（`state/`、`rules/`、`reservation/`）的 `__init__.py`
- [x] 1.2 建立 `config/` 目錄，新增 `config/risk.yaml` 預設範本（FSM 閾值 + 11 規則參數）
- [x] 1.3 在 `pyproject.toml` 宣告依賴：`pydantic>=2`、`pyyaml`、`pytest`、`pytest-asyncio`、`mypy`
- [x] 1.4 設定 `mypy` 嚴格模式（`strict=true`），確保 Protocol 介面被檢查
- [x] 1.5 設定 `ruff` 風格規則並加入 pre-commit hook

## 2. 值物件與型別定義

- [x] 2.1 在 `risk/decision.py` 定義 `Verdict` enum（APPROVE/REJECT/DEFER）與 `Outcome` enum（PASS/CLAMP/REJECT）
- [x] 2.2 在 `risk/decision.py` 定義 `RuleVerdict` frozen dataclass（含 `metadata: dict[str, Any]` 擴充欄位）
- [x] 2.3 在 `risk/decision.py` 定義 `Decision` frozen dataclass，含序列化方法 `to_dict()`
- [x] 2.4 在 `risk/types.py` 定義 `OrderIntent` frozen dataclass（strategy_id、symbol、side、qty、price、signal_id、bar_time、received_at）
- [x] 2.5 在 `risk/types.py` 定義 `Position`、`ReservationResult`、`Event` 基底等共用值物件
- [x] 2.6 為所有值物件補上 `dataclasses.asdict()` 與 `json.dumps` 相容性測試

## 3. Clock 抽象

- [x] 3.1 在 `risk/ports.py` 定義 `Clock` Protocol（`now()` 與 `monotonic()`）
- [x] 3.2 實作 `risk/adapters/system_clock.py` 的 `SystemClock`（使用 `datetime.now(UTC)` 與 `time.monotonic()`）
- [x] 3.3 實作 `tests/fakes/frozen_clock.py` 的 `FrozenClock`，支援 `advance(timedelta)` 與 `set(datetime)`
- [x] 3.4 撰寫 FrozenClock 單元測試：時間前進、tz 處理、monotonic 與 wall-clock 不同步行為

## 4. 配置模型

- [x] 4.1 在 `risk/config.py` 定義 pydantic v2 模型：`FsmThresholds`、`RuleParams`、`ClockConfig`、`RiskConfig`
- [x] 4.2 實作 `RiskConfig.from_yaml(path)` 與啟動時驗證（失敗則 raise，含錯誤路徑）
- [x] 4.3 實作 `RiskConfig.params_hash()` 回傳配置內容 SHA-256
- [x] 4.4 補 `config/risk.yaml` 預設範本對應所有 pydantic 必填欄位
- [x] 4.5 撰寫測試：合法配置載入、缺欄位失敗、型別錯誤失敗、params_hash 確定性
  - 對應 spec scenario: 啟動時配置驗證成功 / 缺欄位阻止啟動 / 型別錯誤阻止啟動

## 5. Ports（DIP 邊界）

- [x] 5.1 在 `risk/ports.py` 定義 `PositionReader` Protocol（read-only：`get_position()`、`list_positions()`）
- [x] 5.2 在 `risk/ports.py` 定義 `MarketDataReader` Protocol（`get_last_price(symbol)`）
- [x] 5.3 在 `risk/ports.py` 定義 `ConfigReader` Protocol（`get(key)`）
- [x] 5.4 在 `risk/ports.py` 定義 `EventPublisher` Protocol（`publish(event)`）並標註 write-only
- [x] 5.5 在 `risk/ports.py` 定義 `StateStore` Protocol（`load_state()`、`save_state(state)`）
- [x] 5.6 撰寫測試：mypy `--strict` 通過、Protocol 不包含具體實作

## 6. 事件總線

- [x] 6.1 在 `risk/events.py` 定義事件基底 `Event`（含 `event_id: UUID`、`at: datetime`）
- [x] 6.2 定義具體事件型別：`StateChanged`、`EmergencyFlattenRequested`、`DecisionEmitted`、`ReservationCreated`、`ReservationReleased`、`ConfigLoaded`、`DailyPnlReset`
- [x] 6.3 實作 `risk/adapters/in_memory_publisher.py` 的 `InMemoryEventPublisher`（asyncio fan-out 給訂閱者）
- [x] 6.4 提供 `subscribe(event_type, handler)` 介面，支援多訂閱者
- [x] 6.5 撰寫測試：事件發布到所有訂閱者、訂閱者間無耦合、序列化往返不失真
  - 對應 spec scenario: 事件可序列化供 SQLite event log

## 7. 狀態機 Layer 1（FSM）

- [x] 7.1 在 `risk/state/states.py` 定義 `SystemState` enum（NORMAL/WARNING/THROTTLED/HALTED/KILL_SWITCH/MAINTENANCE）
- [x] 7.2 在 `risk/state/transitions.py` 定義純函式 `evaluate_transition(current, metrics, config) -> SystemState`，無副作用
- [x] 7.3 在 `risk/state/persistence.py` 實作 `InMemoryStateStore`（符合 `StateStore` Protocol）
- [x] 7.4 在 `risk/state/machine.py` 實作 `StateMachine`：
  - 啟動時從 `StateStore` 讀回狀態（無則 NORMAL）
  - 提供 `tick()` 方法執行轉換
  - 狀態變更發布 `StateChanged` 事件
- [x] 7.5 實作 `StateMachine.start()`：啟動立即執行一次 tick，之後每 60 秒週期執行
- [x] 7.6 實作 KILL_SWITCH 邏輯：進入時發布 `EmergencyFlattenRequested`、開始 4 小時冷靜期計時
- [x] 7.7 實作人工指令：`reset(target)`、`enter_maintenance()`、`exit_maintenance(target)`
- [x] 7.8 實作冷靜期檢查：reset 在冷靜期內回傳具體剩餘時間並拒絕
- [x] 7.9 撰寫單元測試覆蓋所有 spec scenario：
  - 首啟預設 NORMAL、重啟讀回、HALTED 不自動回升
  - 自動轉換（-2% → WARNING、-5% 跳級 → HALTED、-7% → KILL_SWITCH、回升 NORMAL）
  - 人工 reset、KILL_SWITCH 全平事件、冷靜期內拒、冷靜期後解鎖
  - MAINTENANCE 人工進入、MAINTENANCE 拒 OrderIntent
- [x] 7.10 撰寫整合測試：StateMachine + FrozenClock 模擬一日完整 tick 序列

## 8. 規則引擎 Layer 2 框架

- [x] 8.1 在 `risk/rules/base.py` 定義 `RuleContext` dataclass（包裝 OrderIntent + 即時 ports + clock）
- [x] 8.2 在 `risk/rules/base.py` 定義 `RiskRule` Protocol（`evaluate(ctx) -> RuleVerdict`）
- [x] 8.3 在 `risk/rules/base.py` 區分 `RejectRule` 與 `ClampRule` 兩個子 Protocol（為短路機制提供型別保證）
- [x] 8.4 在 `risk/engine.py` 實作 `RuleEngine` 建構：接受 `list[RiskRule]` + ports + clock 注入
- [x] 8.5 實作 `RuleEngine.evaluate(intent) -> Decision`：
  - 依註冊順序評估
  - reject 類短路
  - clamp 類累積套用
  - 最後呼叫 `CapitalReserver.reserve()` 取得 reservation_id（留待 ch.11+12 整合）
- [x] 8.6 實作 clamp 單調遞減 invariant：debug 模式拋例外、production 模式記錄錯誤並忽略修正
- [x] 8.7 發布 `DecisionEmitted` 事件（每筆 Decision 一個）
- [x] 8.8 撰寫測試：
  - reject 短路（後續規則不評估）
  - clamp 累積收斂（10 → 8 → 6 → 5）
  - clamp 違反單調遞減在 debug 模式拋例外
  - DecisionEmitted 事件每筆觸發

## 9. 已實作規則

- [x] 9.1 在 `risk/rules/system_state.py` 實作 `SystemStateRule`：
  - 訂閱 `StateChanged` 事件，快取最新 SystemState
  - 啟動時主動同步查 FSM 取得初始狀態（單次同步呼叫）
  - NORMAL/WARNING → PASS、THROTTLED → CLAMP×0.5、HALTED/KILL_SWITCH/MAINTENANCE → REJECT
- [x] 9.2 撰寫 SystemStateRule 測試覆蓋所有 spec scenario（NORMAL 通過、THROTTLED 縮量、HALTED 拒）
- [x] 9.3 在 `risk/rules/idempotency.py` 實作 `IdempotencyRule`：
  - 內部 LRU 快取（OrderedDict-based 或 cachetools）
  - 預設 TTL 5 分鐘、上限 100,000 筆
  - 從 `ConfigReader` 讀取 TTL 與上限
  - signal_id 命中即 REJECT
- [x] 9.4 撰寫 IdempotencyRule 測試覆蓋所有 spec scenario：
  - 首次出現通過
  - TTL 內重送拒
  - TTL 後重送通過
  - 達上限觸發 LRU 淘汰

## 10. 未實作規則 stub

- [x] 10.1 在 `risk/rules/_stubs.py`（或各檔分散）建立 9 條規則的 Protocol 實作 stub：
  - `SignalFreshnessRule`、`SymbolWhitelistRule`、`StrategyPausedRule`
  - `PerOrderSizeCap`、`StrategyBudgetCap`、`SymbolConcentrationCap`
  - `ThrottleScaler`、`PriceSanityCheck`、`CapitalReservationRule`
- [x] 10.2 每 stub 規則的 `evaluate(ctx)` 拋 `NotImplementedError`，附訊息指向後續 change
- [x] 10.3 每 stub 規則的 docstring 明確描述：用途、入參、出參、配置參數、預期實作策略
- [x] 10.4 撰寫測試：每條 stub 拋出 `NotImplementedError`、簽名與 docstring 存在

## 11. 資金預留 Actor

- [x] 11.1 在 `risk/reservation/ledger.py` 實作 `ReservationLedger`：
  - 三層追蹤：global / per-strategy / per-symbol
  - 提供 `check(intent)` 純函式（無副作用，回傳是否足夠 + 不足項）
  - 提供 `apply(reservation)` 與 `revert(reservation_id)` 寫入操作
- [x] 11.2 在 `risk/reservation/reserver.py` 實作 `CapitalReserver`：
  - 內部 `asyncio.Queue` 序列化請求
  - 單一 worker task 處理（actor 模式）
  - 對外 API：`async reserve(intent) -> ReservationResult`、`async release(reservation_id) -> None`
- [x] 11.3 實作預留三道檢查（per-strategy / per-symbol / global），任一不足即拒並回傳 `reason` 與 `available`
- [x] 11.4 實作 release 冪等性（重複呼叫 no-op，不拋例外）
- [x] 11.5 發布事件 `ReservationCreated`、`ReservationReleased`
- [x] 11.6 撰寫測試：
  - 三道全通過則成功預留
  - 任一不足則拒（per-strategy / per-symbol / global 各一個 case）
  - FCFS 並發測試（asyncio.gather 100 個請求，驗證順序與 ledger 一致性）
  - release 歸還額度 + 事件
  - release 冪等

## 12. RiskGate 門面與啟動流程

- [x] 12.1 在 `risk/gate.py` 實作 `RiskGate` 門面類，作為對外唯一進入點
- [x] 12.2 實作 `RiskGate.from_config(path) -> RiskGate` factory：
  - 載入並驗證 yaml
  - 建構 Clock、StateStore、EventPublisher、CapitalReserver、StateMachine、RuleEngine
  - 依 `rules.enabled` 清單註冊規則（顯式順序）
  - 發布 `ConfigLoaded` 事件含 `params_hash`
- [x] 12.3 實作 `RiskGate.start()`：啟動所有後台任務（FSM tick、Reserver worker），進入 30 秒暖機
- [x] 12.4 實作暖機期：期間 OrderIntent 直接 REJECT（reason `system_warming_up`），可由配置覆寫長度
- [x] 12.5 實作 `RiskGate.evaluate(intent) -> Decision` 對外主介面
- [x] 12.6 實作 `RiskGate.shutdown()` 優雅停機（停 worker、flush 事件）
- [x] 12.7 撰寫測試：
  - 暖機期間 OrderIntent 被拒（reason `system_warming_up`）
  - 暖機結束後 OrderIntent 進入正常 RuleEngine
  - shutdown 後不接受新請求

## 13. 跨日 P&L 重置

- [x] 13.1 實作日內 PnL 計數器，依配置時區（預設 UTC）跨日重置
- [x] 13.2 跨日重置觸發 `DailyPnlReset` 事件
- [x] 13.3 撰寫測試：FrozenClock 從 23:59:59 推進至 00:00:01（UTC）觸發重置與事件

## 14. 整合測試與並發驗證

- [x] 14.1 撰寫整合測試：模擬 100 並發 OrderIntent 通過完整 RuleEngine + CapitalReserver，驗證最終 ledger 與事件序列一致
- [x] 14.2 撰寫整合測試：FSM 從 NORMAL → KILL_SWITCH 全程，驗證 SystemStateRule 即時反應
- [x] 14.3 撰寫整合測試：暖機期完整流程（啟動、首次 tick、暖機期拒單、暖機結束、首筆通過）
- [x] 14.4 撰寫整合測試：服務重啟讀回狀態（StateStore 持久化 + 啟動讀回）
- [x] 14.5 在 CI 加入 `mypy --strict` 與 `pytest -x` gate

## 15. 文件與範本

- [x] 15.1 在 `risk/README.md` 撰寫模組說明：架構、入口、擴充新規則的 SOP
- [x] 15.2 在 `config/README.md` 說明 `risk.yaml` 每個欄位的意義與預設值
- [x] 15.3 補充 `docs/design-brief.md` 交叉引用本 change 的 spec 與 design
- [x] 15.4 在專案 `README.md` 加入 quickstart：如何以 `RiskGate.from_config()` 建立風控閘
- [x] 15.5 整理 11 條規則的契約對照表（已實作 / stub / 未來 change）寫入 `risk/rules/README.md`

## 16. 驗收

- [x] 16.1 執行 `openspec validate add-risk-gate` 通過
- [x] 16.2 全部 41 個 spec scenario 對應到測試（至少一個 test case）
- [x] 16.3 `mypy --strict risk/` 零錯誤
- [x] 16.4 `pytest --cov=risk` 覆蓋率 ≥ 90%（實測 98%）
- [x] 16.5 撰寫部署 checklist 確認 in-memory 持久化的限制與後續 change 預告
