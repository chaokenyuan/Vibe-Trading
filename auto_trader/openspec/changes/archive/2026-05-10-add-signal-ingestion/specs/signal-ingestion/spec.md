## ADDED Requirements

### Requirement: 訊號入口層提供 4 種 SignalSource

`signal-ingestion` capability SHALL 提供 4 個 `SignalSource` adapter：`TradingViewWebhookAdapter`、`ManualCliAdapter`、`VibeShadowScannerAdapter`、`Mt5HttpPushAdapter`。所有 adapter 結構性符合 `SignalSource` Protocol（`async start() -> None` 與 `async stop() -> None`）。

本 change 完整實作 TV Webhook 與 Manual CLI；其餘兩個為 stub（簽名與 docstring 凍結，呼叫 start 即拋 NotImplementedError）。

#### Scenario: TradingViewWebhookAdapter 與 ManualCliAdapter 為完整實作

- **WHEN** 系統啟動 TradingViewWebhookAdapter 或 ManualCliAdapter
- **THEN** adapter SHALL 正常運作，不拋 NotImplementedError

#### Scenario: VibeShadowScannerAdapter 與 Mt5HttpPushAdapter 為 stub

- **WHEN** 嘗試啟動 VibeShadowScannerAdapter 或 Mt5HttpPushAdapter
- **THEN** start() SHALL 拋出 NotImplementedError，附訊息指向後續 change

#### Scenario: 4 adapter 結構性符合 SignalSource Protocol

- **WHEN** 對任一 adapter 執行 `isinstance(adapter, SignalSource)`（runtime_checkable）
- **THEN** SHALL 回傳 True

---

### Requirement: Signal 為不可變正規化值物件

`Signal` SHALL 為 frozen dataclass，包含以下欄位：

- `schema_version: int`（預設 1）
- `signal_id: str`（由 SignalRouter 計算，去重用主鍵）
- `strategy_id: str`
- `strategy_version: str`
- `params_hash: str`
- `symbol: str`
- `side: Literal["BUY","SELL","CLOSE"]`
- `qty: Decimal`
- `price: Decimal | None`
- `bar_time: datetime`（K 線時間，含 tz）
- `interval: str`
- `received_at: datetime`（SignalRouter 注入的 clock.now()）
- `source: Literal["tradingview","mt5","vibe_shadow","manual"]`
- `comment: str | None`
- `raw_payload: dict[str, Any]`（原始輸入，供審計）

`signal_id` SHALL 由 `sha256(strategy_id|symbol|side|bar_time_iso|interval)` 計算。

#### Scenario: signal_id 由固定欄位確定計算

- **WHEN** 兩筆 raw payload 的 `strategy_id`、`symbol`、`side`、`bar_time`、`interval` 完全相同
- **THEN** 經 SignalRouter 補齊後 SHALL 產生相同的 signal_id

#### Scenario: received_at 不影響 signal_id

- **WHEN** 同一 raw payload 在不同 received_at 通過 SignalRouter
- **THEN** 兩次產生的 signal_id SHALL 相同（received_at 不在 hash 輸入內）

#### Scenario: Signal 不可變

- **WHEN** 嘗試修改 Signal 任一欄位
- **THEN** SHALL 拋出 dataclasses.FrozenInstanceError

#### Scenario: Signal 可序列化為 JSON

- **WHEN** 任一 Signal 呼叫 to_dict() 並 json.dumps
- **THEN** SHALL 完整序列化（Decimal 為 string、datetime 為 ISO、Enum 為 value、dict 遞迴）

---

### Requirement: SignalRouter 集中處理去重與下游分發

`SignalRouter` SHALL 訂閱所有 `SignalSource` 的訊號，執行：

1. 補齊 metadata：從 `StrategyRegistry` 查 `strategy_version` 與 `params_hash`；strategy 不存在則拒絕並記錄
2. 計算 `signal_id`
3. 查 `SignalDedupe`，已存在於 TTL 內即拒絕（不分發）
4. 寫入去重快取
5. fan-out 至所有註冊的 `SignalConsumer`

任一 SignalConsumer 失敗 SHALL 不影響其他 consumer 接收訊號（透過 logger.exception 記錄）。

#### Scenario: 多 consumer fan-out

- **WHEN** 兩個 SignalConsumer 註冊到同一 SignalRouter，且 router 收到一筆 raw 訊號
- **THEN** 兩個 consumer SHALL 各自收到一份 Signal

#### Scenario: 一個 consumer 失敗不影響其他

- **WHEN** consumer A 拋例外，consumer B 正常
- **THEN** consumer B SHALL 仍收到 Signal，A 的例外被記錄不向上拋

#### Scenario: TTL 內重送被去重

- **WHEN** 同一 signal_id 在 5 分鐘內第二次到達 SignalRouter
- **THEN** SHALL 不分發給任何 consumer
- **AND** 記錄為 dedupe hit

#### Scenario: TTL 後同 signal_id 視為新訊號

- **WHEN** 同一 signal_id 在 5 分鐘 1 秒後重送
- **THEN** SHALL 正常分發，並覆寫去重快取

#### Scenario: 未知 strategy_id 拒絕

- **WHEN** raw 訊號的 strategy_id 在 StrategyRegistry 中不存在
- **THEN** SignalRouter SHALL 不分發
- **AND** 記錄為 unknown_strategy_id 警告

---

### Requirement: TradingViewWebhookAdapter 認證採 URL secret + IP 白名單

`TradingViewWebhookAdapter` SHALL 提供 `POST /webhook/tv/{secret}/{strategy_id}` 端點。

認證流程：

1. 比對 URL 中的 `{secret}` 與配置中的 secret（constant-time 比較）
2. 比對 `request.client.host` 與配置中的 allowed_ips 清單；空清單代表全部接受（測試用）
3. JSON payload 解析失敗回 422
4. 認證失敗回 401，不洩漏失敗原因細節

#### Scenario: secret 正確且 IP 在白名單則通過

- **WHEN** 收到 POST 請求 secret 與 IP 都符合配置
- **THEN** SHALL 回 200 並把 Signal 推進 SignalRouter

#### Scenario: secret 錯誤回 401

- **WHEN** URL secret 與配置不符
- **THEN** SHALL 回 401，body 為 `{"detail": "unauthorized"}`

#### Scenario: IP 不在白名單回 401

- **WHEN** secret 正確但 client IP 不在 allowed_ips 清單（且清單非空）
- **THEN** SHALL 回 401

#### Scenario: 空白名單代表測試模式接受全部

- **WHEN** 配置 allowed_ips 為空清單，且 secret 正確
- **THEN** SHALL 接受任何 IP

#### Scenario: 無效 JSON 回 422

- **WHEN** 收到 secret 正確但 body 非有效 JSON
- **THEN** SHALL 回 422，不影響後續請求

---

### Requirement: TradingView alert message 解析為 canonical Signal

`TradingViewWebhookAdapter` SHALL 解析以下 JSON schema 為 canonical Signal：

```json
{
  "v": 1,
  "strategy_id": "<id>",
  "symbol": "<sym>",
  "side": "BUY|SELL|CLOSE",
  "qty": "<decimal-string>",
  "price": "<decimal-string-or-null>",
  "bar_time": "<iso8601-with-tz>",
  "interval": "<tv-interval>",
  "comment": "<str-or-null>"
}
```

`source` SHALL 設為 `"tradingview"`、`raw_payload` SHALL 保留完整 JSON、`received_at` 由 SignalRouter 注入。

#### Scenario: 標準 TV payload 解析成功

- **WHEN** 收到合法 JSON 含所有必填欄位
- **THEN** 產出 Signal，欄位逐一對應

#### Scenario: 缺欄位的 payload 拒絕

- **WHEN** payload 缺少 `strategy_id`
- **THEN** SHALL 回 422，不推進 router

#### Scenario: schema_version 不為 1 拒絕

- **WHEN** payload `v` 為 2（未來版本）
- **THEN** SHALL 回 422，標記未支援版本

---

### Requirement: ManualCliAdapter 直接接受 Signal 物件

`ManualCliAdapter` SHALL 提供 `async submit(signal: Signal) -> None`，把 Signal 直接推進 SignalRouter，不執行 webhook 認證。

主要用途：開發測試與緊急人工補單。`source` 必須為 `"manual"`。

#### Scenario: 直接 submit 成功

- **WHEN** 呼叫 adapter.submit(signal) 且 signal.source=="manual"
- **THEN** SHALL 將該 Signal 推進 SignalRouter，正常去重、補 metadata、分發

#### Scenario: source 不為 manual 拒絕

- **WHEN** 呼叫 adapter.submit(signal) 且 signal.source=="tradingview"
- **THEN** SHALL 拋 ValueError

---

### Requirement: SignalDedupe 為 LRU + TTL 快取

`SignalDedupe` SHALL 維護以 `signal_id` 為主鍵的快取：

- TTL：預設 300 秒（5 分鐘），可由配置覆寫
- 上限：預設 100,000 筆，超出時 LRU 淘汰最早條目
- 透過注入的 `Clock.monotonic()` 計算 TTL

#### Scenario: 首次 signal_id 通過

- **WHEN** signal_id "abc" 首次呼叫 dedupe.is_duplicate("abc")
- **THEN** SHALL 回 False
- **AND** 快取此後包含 "abc"

#### Scenario: TTL 內重複偵測

- **WHEN** signal_id "abc" 已在快取中（30 秒前）
- **THEN** dedupe.is_duplicate("abc") SHALL 回 True

#### Scenario: TTL 過期後不視為重複

- **WHEN** signal_id "abc" 在 TTL（300 秒）後重新查詢
- **THEN** dedupe.is_duplicate("abc") SHALL 回 False
- **AND** 快取被覆寫為新時間戳

#### Scenario: 上限觸發 LRU 淘汰

- **WHEN** 快取達 max_entries 且新 signal_id 寫入
- **THEN** 最早條目 SHALL 被淘汰

---

### Requirement: 配置以 YAML 表達且啟動時驗證

`config/signal_ingestion.yaml` SHALL 經 pydantic v2 驗證，schema 包含：

- `tradingview.secret: str`（部署時注入，不入 git）
- `tradingview.allowed_ips: list[str]`（預設 4 個 TV IP）
- `dedupe.ttl_seconds: int`（預設 300）
- `dedupe.max_entries: int`（預設 100000）
- `webhook.rate_limit_per_second: int`（預設 10）
- `scanner.schedule: str`（cron expression，stub 不使用）

驗證失敗 SHALL 阻止啟動。

#### Scenario: 合法配置載入成功

- **WHEN** YAML 含所有必填欄位且型別正確
- **THEN** SHALL 成功載入

#### Scenario: 缺 secret 阻止啟動

- **WHEN** YAML 缺 `tradingview.secret`
- **THEN** SHALL raise pydantic.ValidationError

#### Scenario: 預設 allowed_ips 包含 TV 官方 IP

- **WHEN** 配置未指定 allowed_ips
- **THEN** SHALL 使用 TradingView 4 個官方 IP 為預設

---

### Requirement: StrategyRegistry stub 提供唯讀介面凍結

`StrategyRegistryProtocol` SHALL 暴露 `get_strategy_metadata(strategy_id: str) -> StrategyMetadata | None` 方法。`StrategyMetadata` 含 `strategy_id`、`strategy_version`、`params_hash` 三欄位（frozen dataclass）。

本 change 提供 `InMemoryStrategyRegistry` 實作，後續 strategy-host change 提供完整版本。

#### Scenario: 已註冊的 strategy 回傳 metadata

- **WHEN** registry 已含 strategy_id="A" 的條目
- **THEN** get_strategy_metadata("A") SHALL 回傳 StrategyMetadata 實例

#### Scenario: 未註冊回傳 None

- **WHEN** registry 不含 strategy_id="X" 的條目
- **THEN** get_strategy_metadata("X") SHALL 回傳 None

---

### Requirement: 所有時間相依邏輯透過 Clock Protocol 注入

`signal-ingestion` 全部時間相依邏輯（dedupe TTL、received_at 注入、scanner schedule）SHALL 透過注入的 `Clock` Protocol 取得時間，禁止直接呼叫 `datetime.now()`。

#### Scenario: 注入測試 Clock 控制 TTL

- **WHEN** 測試注入 FrozenClock 並呼叫 advance(timedelta(minutes=6))
- **THEN** dedupe SHALL 視 TTL 已過期

---

### Requirement: SignalRouter 啟停為 async lifecycle

`SignalRouter` SHALL 提供 `async start()` / `async stop()`，啟動所有註冊的 SignalSource、優雅停機。重複 start SHALL raise；stop 為冪等。

#### Scenario: start 成功啟動所有 source

- **WHEN** router 註冊 N 個 source 並呼叫 start()
- **THEN** 每個 source 的 start() SHALL 被呼叫

#### Scenario: 重複 start 拋例外

- **WHEN** 對已啟動的 router 再呼叫 start()
- **THEN** SHALL raise RuntimeError

#### Scenario: stop 冪等

- **WHEN** 對未啟動或已停止的 router 呼叫 stop()
- **THEN** SHALL 為 no-op，不拋例外
