# observability capability

稽核日誌（JSON Lines）+ 告警（AlertSink）+ 健康檢查（FastAPI /health）。

## 模組結構

```
observability/
├── audit_log.py        AuditLogWriter（訂閱 EventPublisher 寫 JSON Lines）
├── ports.py            AlertSink Protocol
├── alert_router.py     AlertRouter（事件 → 告警分類）
├── health.py           create_health_app（/health + /readyz）
├── config.py           ObservabilityConfig
└── adapters/
    ├── logging_sink.py  LoggingAlertSink（stdlib logger）
    └── telegram_stub.py TelegramAlertSink stub
```

## 對外進入點

```python
from observability.adapters.logging_sink import LoggingAlertSink
from observability.alert_router import AlertRouter
from observability.audit_log import AuditLogWriter
from observability.health import create_health_app

# 啟動 audit log
audit = AuditLogWriter(publisher=event_publisher, log_path="logs/audit.jsonl")
audit.start()

# 啟動告警
sink = LoggingAlertSink()
alert_router = AlertRouter(publisher=event_publisher, sink=sink)
alert_router.start()

# Health endpoint（部署層 mount 到主 app 或單獨 uvicorn）
health_app = create_health_app(clock=system_clock)
```

## 告警事件白名單

| 事件 | Level | 說明 |
|------|-------|------|
| EmergencyFlattenRequested | critical | KILL_SWITCH 觸發 |
| OrderRejectedByBroker | error | 交易所拒單 |
| StateChanged → HALTED/THROTTLED | warning | FSM 降級 |
| StateChanged → 其他 | info | FSM 變遷 |
| ConfigLoaded | info | 配置載入 |
| DailyPnlReset | info | 跨日重置 |

非白名單事件（DecisionEmitted、ReservationCreated 等高頻事件）不觸發告警。

## 後續 change 預告

- 真實 Telegram bot 整合（取代 TelegramAlertSink stub）
- Prometheus metrics endpoint
- SQLite event store（取代 / 補強 JSON Lines）
- Grafana dashboard 範本
