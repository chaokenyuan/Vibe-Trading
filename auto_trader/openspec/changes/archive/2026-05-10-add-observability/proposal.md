## Why

5 個 capability 已能跑端到端，但無持久化稽核紀錄、無告警通道、無健康檢查。本 change 補上系統可觀察性。

## What Changes

新增 `observability` capability：

- `AuditLogWriter`：訂閱 EventPublisher 把所有事件寫成 JSON Lines（每行一筆事件 to_dict 結果）
- `AlertSink` Protocol：告警出口抽象
- `LoggingAlertSink`：用 stdlib logging 輸出告警（production 可用、stdout 路由）
- `TelegramAlertSink`：stub（後續 change 接 Telegram bot API）
- `AlertRouter`：訂閱關鍵事件（KILL_SWITCH、OrderRejectedByBroker、Strategy FAILED 等）轉送 AlertSink
- `create_health_app`：FastAPI factory 提供 `/health` 與 `/readyz` endpoint

### 範圍外

- 真實 Telegram bot 整合（保留 stub）
- Prometheus metrics（後續 change）
- 結構化 SQLite event store（用 JSON Lines 已可，更精細查詢屬後續 change）

## Capabilities

### New Capabilities

- `observability`：稽核日誌、告警、健康檢查

### Modified Capabilities

無。

## Impact

新模組：

```
observability/
├── audit_log.py        AuditLogWriter
├── ports.py            AlertSink Protocol
├── alert_router.py     AlertRouter
├── health.py           create_health_app
├── config.py           ObservabilityConfig
└── adapters/
    ├── logging_sink.py LoggingAlertSink
    └── telegram_stub.py TelegramAlertSink stub
```

依賴：無新外部依賴（FastAPI 已在 signal-ingestion 引入）。

對未來 capability 承諾：
- 後續可加 prometheus / grafana / SQLite event store
- 後續實作 TelegramAlertSink 真實版
