## ADDED Requirements

### Requirement: AuditLogWriter 把事件寫 JSON Lines

`AuditLogWriter` SHALL 訂閱 EventPublisher，每收到事件即把 `event.to_dict()` 序列化為 JSON 並追加一行至指定檔案。

#### Scenario: 寫入單行 JSON

- **WHEN** AuditLogWriter 訂閱後 publisher 發 1 個事件
- **THEN** 目標檔 SHALL 新增 1 行有效 JSON

#### Scenario: 多事件多行

- **WHEN** publisher 連續發 N 個事件
- **THEN** 目標檔 SHALL 含 N 行
- **AND** 每行為單獨可解析的 JSON object

#### Scenario: 事件 to_dict 失敗時不拖垮 publisher

- **WHEN** 某事件呼叫 to_dict() 拋例外
- **THEN** AuditLogWriter SHALL 紀錄 error 但不向上拋
- **AND** 後續事件 SHALL 仍正常寫入

---

### Requirement: AlertSink Protocol 統一告警出口

`AlertSink` Protocol SHALL 暴露 `async send(level: str, message: str, context: dict) -> None`。
`LoggingAlertSink` 為完整實作（用 stdlib logger）。
`TelegramAlertSink` 為 stub（呼叫 send 即拋 NotImplementedError）。

#### Scenario: LoggingAlertSink 結構符合 Protocol

- **WHEN** isinstance(LoggingAlertSink(), AlertSink)
- **THEN** SHALL 回 True

#### Scenario: LoggingAlertSink 呼叫 stdlib logger

- **WHEN** 呼叫 sink.send("error", "msg", {"k": "v"})
- **THEN** 對應 level 的 logger SHALL 收到日誌紀錄

#### Scenario: TelegramAlertSink stub 拋 NotImplementedError

- **WHEN** 呼叫 TelegramAlertSink().send(...)
- **THEN** SHALL 拋 NotImplementedError

---

### Requirement: AlertRouter 過濾關鍵事件轉發告警

`AlertRouter` SHALL 訂閱整個 Event 基底，依內建白名單把以下事件轉為告警：

- `StateChanged`：level=warning 或 error（依 to_state 決定）
- `EmergencyFlattenRequested`：level=critical
- `OrderRejectedByBroker`：level=error
- `ConfigLoaded`：level=info
- `DailyPnlReset`：level=info

非白名單事件 SHALL 不觸發告警。

#### Scenario: KILL_SWITCH 事件觸發 critical 告警

- **WHEN** publisher 發 EmergencyFlattenRequested
- **THEN** AlertSink SHALL 收到 critical 告警

#### Scenario: 不在白名單事件不告警

- **WHEN** publisher 發 DecisionEmitted
- **THEN** AlertSink SHALL 不被呼叫

---

### Requirement: HealthEndpoint 提供 /health

`create_health_app(...)` SHALL 回 FastAPI app 含 `GET /health` 與 `GET /readyz` 端點。

`/health` 回 200 + JSON `{status, service, version, started_at_iso}`。
`/readyz` 回 200 if 所有元件 ready，否則 503。

#### Scenario: /health 回 200

- **WHEN** GET /health
- **THEN** SHALL 回 status_code=200，body 含 status="ok"
