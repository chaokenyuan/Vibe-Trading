# add-observability — 驗收紀錄

## 驗證

```
$ openspec validate add-observability → valid
$ mypy risk/ signals/ strategies/ execution/ reconciliation/ observability/ tests/
  → 109 source files clean
$ pytest -q → 385 passed
$ ruff check → All clean
```

## Spec scenario 對測試對照

| Requirement | 覆蓋測試 |
|-------------|---------|
| LoggingAlertSink 結構 | `test_observability.py::test_logging_sink_satisfies_protocol`, `test_logging_sink_calls_logger` |
| TelegramAlertSink stub | `test_observability.py::test_telegram_stub_satisfies_protocol`, `test_telegram_stub_raises_not_implemented` |
| AuditLogWriter 寫單行 | `test_observability.py::test_audit_log_writes_one_line_per_event` |
| AuditLogWriter 多事件多行 | `test_observability.py::test_audit_log_multiple_events_multiple_lines` |
| AlertRouter KILL_SWITCH critical | `test_observability.py::test_kill_switch_event_triggers_critical_alert` |
| AlertRouter HALTED warning | `test_observability.py::test_state_changed_to_halted_warning` |
| AlertRouter OrderRejectedByBroker error | `test_observability.py::test_order_rejected_by_broker_alert` |
| AlertRouter 非白名單不告警 | `test_observability.py::test_decision_emitted_does_not_alert` |
| Health /health 回 200 | `test_observability.py::test_health_endpoint_returns_200` |
| /readyz 503 when not ready | `test_observability.py::test_readyz_returns_503_when_not_ready` |

## 後續 change 預告

- 實作 TelegramAlertSink 真實 Telegram bot
- 加 Prometheus metrics
- SQLite event store / Grafana dashboard
