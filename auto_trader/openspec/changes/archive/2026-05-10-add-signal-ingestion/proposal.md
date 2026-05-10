## Why

`add-risk-gate` 已完成，但風控閘現在沒有訊號入口 — 沒人會把 `OrderIntent` 餵進 `RiskGate.evaluate()`。
本 change 補上 vibe-auto-trader 的訊號接收層：把外部訊號（TradingView Webhook、Vibe-Trading 候選掃描、人工 CLI、MT5 EA）轉換為內部正規化的 `Signal`，並交給下游 strategy-host 消費。

設計優先序定位：依 `docs/design-brief.md` 第 10 節的 Capability 撰寫順序，此為「第一批：鎖定危險與多決策」的第二項。

延伸：`docs/design-brief.md` 第 5 節（訊號入口契約，已修訂版）。

## What Changes

- **新增** `signal-ingestion` capability，提供 4 種訊號來源 adapter：

  | Adapter | 路徑 | 訊號級別 | 本 change 範圍 |
  |---------|------|---------|---------------|
  | `TradingViewWebhookAdapter` | TV Pine alert → FastAPI POST | 真實市場 | **完整實作**（MVP 主路徑） |
  | `ManualCliAdapter` | 命令列直接餵訊號 | 測試／補單 | **完整實作**（開發必備） |
  | `VibeShadowScannerAdapter` | Vibe-Trading 的 `scan_shadow_signals` 拉取 | 研究級候選 | **stub**（簽名凍結，後續 change 實作） |
  | `Mt5HttpPushAdapter` | 自寫 MT5 EA 透過 HTTP 推送 | 真實市場（FX） | **stub** |

- **新增** `Signal` canonical 值物件（frozen dataclass，schema_version=1）：
  - 從 webhook 解析欄位 + SignalRouter 補齊 metadata
  - `source: Literal["tradingview","mt5","vibe_shadow","manual"]`
  - `signal_id` 由 `sha256(strategy_id|symbol|side|bar_time|interval)` 自動生成
  - `received_at` 由 Clock 注入

- **新增** `SignalSource` Protocol（write-only：`async start() / stop()`）

- **新增** `SignalConsumer` Protocol（write-only：`async on_signal(signal: Signal)`）
  - 跨 capability 邊界，由 strategy-host 後續實作

- **新增** `SignalRouter`：訂閱所有 `SignalSource`，補齊 metadata（strategy_version、params_hash）、執行去重、呼叫所有 `SignalConsumer`

- **新增** `SignalDedupe`：以 `signal_id` 為主鍵的 5 分鐘 TTL 快取（與 `IdempotencyRule` 結構雷同但獨立實例，避免跨 capability 耦合）

- **新增** `StrategyRegistry` 唯讀 stub：strategy-host capability 將實作完整版本，本 change 僅提供最小介面（`get_strategy_metadata(strategy_id) -> StrategyMetadata`）讓 SignalRouter 補齊 metadata

- **新增** TradingView Webhook 端點：
  - 路徑：`POST /webhook/tv/{secret}`
  - 認證：URL secret token + IP 白名單（TV 4 個官方 IP）
  - 速率限制（每秒 N 個，避免被 DDoS）
  - 強制 https（部署時由 reverse proxy 處理；本 capability 不擔保）

- **新增** 配置：`config/signal_ingestion.yaml`（webhook secret、allowed IPs、scanner schedule、dedupe TTL）

### 範圍外（留給後續 change）

- VibeShadowScannerAdapter 與 Mt5HttpPushAdapter 的具體拉取／接收邏輯
- StrategyRegistry 的完整實作（屬 strategy-host）
- SignalConsumer 的下游消費（屬 strategy-host）
- 訊號到 OrderIntent 的轉換（屬 strategy-host）
- WebSocket 訊號來源
- Discord / Telegram / Slack 訊號來源

## Capabilities

### New Capabilities

- `signal-ingestion`：訊號入口層。提供
  - 4 種 SignalSource adapter（TV Webhook 與 Manual CLI 完整實作；Vibe Shadow 與 MT5 為 stub）
  - SignalRouter 訂閱與分發
  - SignalDedupe 5 分鐘 TTL
  - 認證（URL secret + IP 白名單）
  - canonical Signal 值物件

### Modified Capabilities

無。

## Impact

### 程式碼結構（新增）

```
signal/
├── __init__.py
├── types.py                 Signal frozen dataclass + SignalSource enum
├── ports.py                 SignalSource / SignalConsumer Protocol
├── router.py                SignalRouter（訂閱 sources、去重、分發 consumers）
├── dedupe.py                SignalDedupe（TTL + LRU 快取）
├── config.py                pydantic SignalIngestionConfig
├── registry_stub.py         StrategyRegistry 唯讀 stub（後續 strategy-host change 取代）
├── adapters/
│   ├── tradingview.py       TradingViewWebhookAdapter（FastAPI app）
│   ├── manual_cli.py        ManualCliAdapter
│   └── stubs.py             VibeShadowScannerAdapter / Mt5HttpPushAdapter（stub）
└── auth.py                  URL secret token + IP 白名單驗證
```

### 配置

- 新增 `config/signal_ingestion.yaml`

### 依賴

- 新增 `fastapi >= 0.110`、`uvicorn[standard] >= 0.27`、`httpx`（測試用）
- 既有 pydantic v2 / pyyaml / pytest 已涵蓋

### 對未來 capability 的契約承諾

- `strategy-host` 將實作 `SignalConsumer`，註冊到 `SignalRouter`
- `strategy-host` 將提供 `StrategyRegistry` 完整實作，取代本 change 的 stub
- `observability` 將訂閱 `SignalRouter` 的事件（後續加事件型別）

### 風險與權衡

- **TV 不支援 HMAC**：只能靠 URL secret + IP 白名單，是 spec 接受的權衡（風險已記錄於 design-brief 第 5 節）
- **去重快取重啟丟失**：MVP in-memory，後續 SQLite change 補上
- **VibeShadowScannerAdapter stub**：研究級訊號路徑暫時無實作，但介面凍結，後續 change 不需修改 SignalRouter
- **FastAPI lifespan 與 RiskGate 整合**：本 change 提供 SignalRouter 啟停 API，由更上層（serving entry point）統籌組合
