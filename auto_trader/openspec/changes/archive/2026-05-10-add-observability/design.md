## Context

可觀察性是系統的「黑盒記錄器」與「告警通道」。本 change 提供：
- 稽核：所有事件寫 JSON Lines（每行一筆 event.to_dict）
- 告警：AlertSink Protocol + LoggingAlertSink（生產可用） + Telegram stub
- 健康：FastAPI /health 端點

## Goals / Non-Goals

### Goals

1. AuditLogWriter 訂閱所有事件並寫檔（async，避免阻塞主流程）
2. AlertSink 抽象讓告警通道可換（logging / Telegram / Slack ...）
3. AlertRouter 過濾關鍵事件轉送 AlertSink
4. /health 端點不需認證，回 service 狀態

### Non-Goals

1. 不實作 Telegram 真實 bot
2. 不做 Prometheus metrics
3. 不做 SQL 化 event store
4. 不做 Grafana dashboard

## Decisions

### D-1：AuditLogWriter 寫 JSON Lines（每行一個 event）

**決策**：每收到 event → 呼叫 event.to_dict() → json.dumps → 寫入檔案 + `\n`。

**替代方案**：
- 寫 SQLite：好查詢，但複雜度高
- 寫 stdout：好 ship 到 ELK，但本機開發累

**理由**：
- JSON Lines 簡單，可被 jq/awk/grep 直接讀
- 後續可視需求加 SQLite layer，不影響現有寫檔
- 支援 log rotation（簡單實作 size-based）

### D-2：AlertRouter 內建關鍵事件過濾

**決策**：AlertRouter 訂閱整個 EventPublisher，內部白名單 N 種事件 → 轉送 AlertSink。

過濾的事件：
- StateChanged（FSM 變遷）
- EmergencyFlattenRequested
- OrderRejectedByBroker
- ConfigLoaded（啟動確認）
- DailyPnlReset

**理由**：
- 中央化過濾比每個事件源各自決定告警邏輯簡單
- 訂閱整個 Event 基底，事件擴充自動納入篩選範圍

### D-3：/health 不要求認證

**決策**：health 端點公開，不需 secret。

**理由**：
- 標準業界做法（K8s / load balancer 做 health check）
- 內容只是 service 名 + 版本 + uptime，無敏感資訊

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| **R-1** AuditLogWriter 寫檔阻塞事件循環 | 用 async file open + write；MVP 接受 fsync 同步 |
| **R-2** Audit log 無上限增長 | 後續加 size-based rotation；本 change 不做 |
| **R-3** AlertSink 故障導致告警漏 | LoggingAlertSink 寫 stdlib logger（不會失敗）；其他 sink 容錯由 AlertRouter 提供 |
