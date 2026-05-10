## Context

`signal-ingestion` 是訊號的「第一站」：把外部世界（TradingView、Vibe-Trading、CLI、MT5）的訊號變成內部正規化的 `Signal`，並交給下游消費者。

當前狀態：

- `risk-gate` capability 已就緒；`OrderIntent` → `Decision` 通路完整
- 訊號到 `OrderIntent` 的轉換屬 `strategy-host`，本 change 僅做到 `Signal`
- `docs/design-brief.md` 第 5 節（補課修訂版）已定義訊號入口契約與 4 條路徑

關鍵約束：

- **延遲容忍**：使用者明確接受秒級延遲，因此可以用 Python async + queue 緩衝
- **TV 不支援 HMAC**：只能 URL secret + IP 白名單；TLS 由 reverse proxy 守
- **多策略並行**：4 個 adapter 可同時運作，訊號去重必須跨 source 共用主鍵
- **回測再現性**（design-brief E3）：每筆 Signal 必須帶完整 metadata（strategy_version、params_hash、source、raw_payload）供後續審計與重放

利害關係人：

- **使用者**：TV 端會手動為每個策略設定 alert，期望 webhook URL 穩定
- **strategy-host 開發者**：會實作 `SignalConsumer`，需要清楚的 Signal schema
- **稽核視角**：每筆 Signal 連同 raw_payload 寫入審計（後續 SQLite change）

## Goals / Non-Goals

### Goals

1. 把 4 條訊號路徑落為 4 個 SignalSource 實作；介面統一（Protocol），實作策略各異
2. canonical `Signal` 值物件凍結 schema（含 `schema_version` 欄位以利後續演進）
3. 認證機制（URL secret + IP 白名單）為 production-ready；測試與 production 共用同一套
4. SignalRouter 解耦 source 與 consumer：source 不認識下游、consumer 不認識上游
5. 去重在 router 層集中處理，跨 source 共用 TTL 快取
6. metadata 補齊（strategy_version / params_hash）與訊號原始 payload 並存，可重建任一時刻完整訊號

### Non-Goals

1. 不實作 strategy-host（SignalConsumer 由其後續實作）
2. 不實作訊號到 OrderIntent 的轉換邏輯
3. 不負責 webhook 服務的 TLS 終止（由 reverse proxy 守）
4. 不負責 webhook 公開 URL 的派發（由 deployment 層處理）
5. 不在本 change 把 Vibe-Trading 真的串起來（VibeShadowScannerAdapter 為 stub）
6. 不支援訊號取消（design-brief R9 凍結為「不處理，先讓單跑完」）
7. 不支援訊號 update（D6 凍結為「拒絕重送」）

## Decisions

### D-1：SignalRouter 集中處理去重，而非各 adapter 自行去重

**決策**：SignalDedupe 為 router 層的單例快取；adapter 只負責解析與認證，不處理去重。

**替代方案**：

- 各 adapter 自行去重：跨 source 不能共用快取（兩個 source 收到同一 signal_id 不會被識別為重複）
- IdempotencyRule 共用：跨 capability 耦合，且兩者在系統中位置不同（IdempotencyRule 是 OrderIntent 階段，這裡是 Signal 階段）

**理由**：

- 單例快取保證跨 source 一致性
- 去重在最早階段處理，後續 strategy-host 不必再做（已為 strategy-host 開發者明確介面契約）
- 與 IdempotencyRule 邏輯雷同但獨立實例：明確 SRP 邊界

### D-2：Signal source 為 Protocol，而非繼承

**決策**：`SignalSource` 為 Protocol（write-only：`start/stop`）；adapter 用結構性 typing。

**替代方案**：

- ABC 抽象基底類別：要求顯式繼承，違反鴨子型別精神
- 一個大 Adapter class 處理所有 source：違反 SRP

**理由**：

- 測試替身可不繼承 Protocol 即可結構性符合
- adapter 可獨立演化，互不影響
- 與 risk-gate 的 ports.py 設計風格一致

### D-3：認證採「URL secret + IP 白名單」雙因素，無 HMAC

**決策**：

- TradingView 不支援自訂 header／HMAC，所以無法做標準的簽章驗證
- URL secret 嵌在路徑：`POST /webhook/tv/{secret}/{strategy_id}`
- IP 白名單預設 4 個 TradingView 官方 IP（可由 config 覆寫，便於本機測試）
- secret token 為 32 字元 url-safe base64（建議由 deployment 產生並寫入 config）
- TLS 強制 https，由 reverse proxy（Cloudflare／Caddy）守

**替代方案**：

- 只 URL secret：URL 流出（瀏覽器歷史、log）即破
- 只 IP 白名單：TV IP 不公開保證、可能變動
- 自寫 HMAC by IP source：TV 不支援自訂 header

**理由**：

- 雙因素互補：secret 防止 IP 偽造（外部攻擊者）、IP 白名單防止 secret 流出後濫用
- 是 spec 接受的折衷（design-brief 第 5 節已記錄）

### D-4：Signal 與 risk.types.OrderIntent 為兩個獨立值物件

**決策**：

- `Signal` 在 `signal/types.py`（本 change）
- `OrderIntent` 在 `risk/types.py`（既有）
- strategy-host 負責 `Signal → OrderIntent` 轉換（不在本 change）

**替代方案**：

- 統一為一個 `Signal`（用作 OrderIntent）：strategy 對訊號的解讀是業務邏輯，不應在訊號層處理
- 把 OrderIntent 移入 signal/：違反既有 risk-gate spec

**理由**：

- 每層各司其職（SRP）
- Signal 帶 raw_payload 可重放，OrderIntent 已是「策略決定」後的結果
- 為回測再現性鋪路：拿同一個 Signal，重跑同一 strategy_version + params_hash 應得到同樣 OrderIntent

### D-5：FastAPI app 由本 capability 提供，但不啟動 server

**決策**：

- 本 capability 提供 `create_tradingview_app(adapter) -> FastAPI` factory
- 不啟動 uvicorn server（屬於 deployment／serving 層）
- 測試使用 `httpx.AsyncClient(transport=ASGITransport(app=...))` 直接發請求，無需開 socket

**替代方案**：

- 自啟動 uvicorn：與部署架構耦合，難以複用
- 不用 FastAPI 而手寫 ASGI handler：學習成本高、缺少 OpenAPI doc

**理由**：

- ASGITransport 測試模式比起真實 HTTP 快 10× 以上
- factory 模式讓 deployment 層自由組裝（單獨服務 / 與其他 app 合併）

### D-6：StrategyRegistry 在本 change 為唯讀 stub

**決策**：本 change 提供 `StrategyRegistryProtocol`（minimal API：`get_strategy_metadata(id) -> StrategyMetadata | None`）+ `InMemoryStrategyRegistry`（測試與 MVP 用）。完整版本含註冊／註銷／生命週期由 `add-strategy-host` change 實作。

**替代方案**：

- 等到 strategy-host change 才開發 signal-ingestion：耦合過重，無法獨立進度
- 把完整 StrategyRegistry 放本 change：超出 SRP 邊界

**理由**：

- 介面凍結，後續 change 只需替換 implementation
- 測試友善：可任意建構 InMemoryStrategyRegistry
- 對外行為與最終實作 99% 一致（差異僅為熱載入／生命週期）

### D-7：訊號 received_at 與 bar_time 嚴格區分

**決策**：

- `bar_time`：來自 webhook payload（TV 端 K 線時間）
- `received_at`：由 SignalRouter 注入的 `clock.now()`
- `signal_id`：以 `bar_time + interval + strategy_id + symbol + side` 計算 SHA-256

**替代方案**：

- 只用 received_at：同 bar 重觸發會撞 ID
- 把 received_at 納入 signal_id 計算：失去去重意義

**理由**：

- bar_time 帶語意（哪根 K 線）；received_at 帶 traceability（什麼時候到我們）
- signal_id 不含 received_at 確保「同 bar、同方向」可去重

### D-8：SignalRouter 對 SignalConsumer 採 fan-out + 故障隔離

**決策**：

- 多個 SignalConsumer 可註冊
- 任一 consumer 失敗不影響其他（與 InMemoryEventPublisher 設計一致）
- 失敗透過 logging 記錄

**替代方案**：

- 嚴格鏈式：consumer A 失敗則不送 B（語意奇怪）
- 不允許多 consumer：缺乏彈性

**理由**：

- 與 EventPublisher 設計一致，降低 mental model 負擔
- 適合「strategy-host 主消費 + observability 旁路審計」的多訂閱場景

### D-9：訊號 schema 版本欄位

**決策**：`Signal` 含 `schema_version: int`，預設值 1。後續修改 schema 時版本號加 1，舊版 schema 透過 migration 函式轉換或拒絕。

**替代方案**：

- 不帶版本：未來 breaking change 痛苦
- 帶 string version：弱於 int 比對

**理由**：

- 與 TV alert message JSON 模板一致（`"v": 1`）
- 簡單明確

### D-10：CLI Adapter 不啟動長期 process，而是 one-shot

**決策**：`ManualCliAdapter` 提供 `submit(signal: Signal)` 方法，不開 stdin loop。CLI 工具是外部 wrapper（`scripts/submit_signal.py`），呼叫 adapter 後退出。

**替代方案**：

- adapter 內部讀 stdin：難以測試、生命週期模糊
- adapter 啟動 server 接收 CLI：過度工程

**理由**：

- 測試簡單（單元函式級）
- CLI 工具的 process 管理不是 capability 的職責

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| **R-1 TV IP 變動**：TradingView 變更 webhook IP 列表 | 配置可覆寫；發現後 hotfix yaml + 重啟 |
| **R-2 Webhook DDoS**：URL secret 流出後被亂打 | 速率限制（per IP 每秒 N 個）+ secret 輪替 SOP |
| **R-3 訊號重送風暴**：同 signal_id 短時間內被重送 100 次 | SignalDedupe 5 分鐘 TTL 命中即拒；測試覆蓋 |
| **R-4 SignalConsumer 失敗連鎖**：consumer 拋例外 | 故障隔離（D-8）+ 透過 logger.exception 記錄 |
| **R-5 schema 演進造成舊 source 失效**：例如 TV alert message 格式改變 | `schema_version` 欄位 + 拒絕未知版本 + log 警告 |
| **R-6 secret 從 git 流出** | secret 必須由 env var 或 secrets manager 注入，永不入 git；spec scenario 含「config 範例不含真 secret」 |
| **R-7 StrategyRegistry stub 與最終實作不一致** | Protocol 凍結介面；後續 change 必須通過既有 signal-ingestion 測試 |
| **R-8 跨 source signal_id collision**：兩個 source 故意/誤用同 signal_id | SignalDedupe 跨 source 共用主鍵會擋；但這代表上游有 bug，需告警 |
| **R-9 received_at 時鐘漂移**：注入的 Clock 與 deploy 真實時鐘不同步 | 透過 SystemClock 實作，部署時同步 NTP；測試使用 FrozenClock |
| **R-10 webhook 大量字串解析消耗**：JSON parse 失敗丟例外傳染 | adapter 層 try/except 並回 422 而非 500；不影響其他訊號 |

## Migration Plan

本 change 為新增，無既有資料需遷移。部署步驟：

1. 建立 `signal/` 套件結構與檔案
2. 建立 `config/signal_ingestion.yaml` 預設範本（不含真 secret）
3. 提供 `SignalRouter.from_config(path, ...)` factory
4. 撰寫單元測試：4 adapter 各自 + router 整合 + dedupe 邊界 + auth 拒絕路徑
5. 撰寫整合測試：`httpx.AsyncClient` + ASGI 模擬完整 webhook 流程
6. 部署層另寫 entry point（不在本 change），組合 SignalRouter + RiskGate

回滾：純新增，刪除 `signal/` 與 `config/signal_ingestion.yaml` 即可。

## Open Questions

1. **Webhook 速率限制策略**：每 IP 每秒幾個合理？預設 10？由 config 控制？建議 spec 中先定 10/s，後續視真實流量調。
2. **secret 輪替頻率**：多久輪替一次？無強制；建議在 deployment 文件記錄而不寫死 spec。
3. **VibeShadowScannerAdapter cron schedule**：每天幾點掃？由 config 還是 hard-code？建議 config（cron expression），但具體值留給 deployment。
4. **Mt5HttpPushAdapter 認證機制**：MT5 EA 可自寫，理論上能加 HMAC。等實作 change 再定，本 change stub 不指定。
5. **Signal 寫入持久化**：SignalRouter 是否該直接寫 SQLite 留底？建議透過 EventPublisher（後續事件型別）讓 observability 訂閱寫入，避免 router 直接寫資料庫。
