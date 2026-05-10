## 1. 骨架

- [x] 1.1 建立 `observability/` 套件 + adapters
- [x] 1.2 pyproject.toml include `observability*`

## 2. AlertSink

- [x] 2.1 `observability/ports.py`：AlertSink Protocol（runtime_checkable）
- [x] 2.2 `observability/adapters/logging_sink.py`：LoggingAlertSink
- [x] 2.3 `observability/adapters/telegram_stub.py`：TelegramAlertSink stub
- [x] 2.4 撰寫測試

## 3. AuditLogWriter + AlertRouter

- [x] 3.1 `observability/audit_log.py`：寫 JSON Lines + 故障容錯
- [x] 3.2 `observability/alert_router.py`：AlertRouter（內建事件白名單）
- [x] 3.3 撰寫測試

## 4. Health endpoint

- [x] 4.1 `observability/health.py`：create_health_app（FastAPI）
- [x] 4.2 撰寫測試（httpx ASGITransport）

## 5. 配置 + 文件

- [x] 5.1 `observability/config.py` ObservabilityConfig
- [x] 5.2 `config/observability.yaml` 預設範本
- [x] 5.3 `observability/README.md`

## 6. 驗收

- [x] 6.1 mypy / pytest / ruff 全綠
- [x] 6.2 acceptance.md
