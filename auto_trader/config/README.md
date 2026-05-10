# config/ — 配置檔目錄

所有配置以 YAML 表達，由 pydantic v2 模型於啟動時驗證（`extra='forbid'`，typo 不容忍）。
配置變更需重啟服務生效（凍結決策 D4，本 capability 不支援 hot reload）。

## risk.yaml — 風控閘配置

完整 schema 由 `risk.config.RiskConfig` 定義；下方為各區段用途速查。

### `fsm` — 系統狀態機配置

| 欄位 | 型別 | 說明 |
|------|------|------|
| `fsm.thresholds.daily_pnl_warning` | float | 日內 PnL 進入 WARNING 的上界（負值，例 -0.02 = -2%） |
| `fsm.thresholds.daily_pnl_throttled` | float | 進入 THROTTLED 的 PnL 上界 |
| `fsm.thresholds.daily_pnl_halted` | float | 進入 HALTED 的 PnL 上界 |
| `fsm.thresholds.daily_pnl_kill` | float | 進入 KILL_SWITCH 的 PnL 上界（最強，跨級觸發） |
| `fsm.thresholds.api_error_rate_throttled` | float | API 錯誤率超過此值進入 THROTTLED（0–1） |
| `fsm.thresholds.kill_switch_cooling_seconds` | int | KILL_SWITCH 觸發後人工 reset 的冷靜期秒數（預設 14400 = 4h） |
| `fsm.tick_interval_seconds` | int | FSM 自動 tick 週期（預設 60） |

### `clock` — 時間抽象配置

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `clock.tz` | str | `UTC` | 跨日 PnL 重置依此時區判斷邊界（接受 `zoneinfo` 可解析的字串，如 `Asia/Taipei`） |

### `warming_up` — 啟動暖機配置

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `warming_up.duration_seconds` | int | 30 | 啟動後拒收 OrderIntent 的時間，給後台元件初始化緩衝 |

### `rules` — 規則啟用清單與參數

#### `rules.enabled`

list[str]，規則名稱清單；**順序即執行順序**（reject 類前段、clamp 類中段、原子預留最後）。

預設：

```yaml
rules:
  enabled:
    - SystemStateRule
    - IdempotencyRule
    - SignalFreshnessRule
    - SymbolWhitelistRule
    - StrategyPausedRule
    - PerOrderSizeCap
    - StrategyBudgetCap
    - SymbolConcentrationCap
    - ThrottleScaler
    - PriceSanityCheck
    - CapitalReservationRule
```

#### `rules.params`

dict[str, dict[str, Any]]，每條規則的參數。

| 規則 | 參數 | 預設 | 說明 |
|------|------|------|------|
| `SystemStateRule` | `throttled_size_scaler` | 0.5 | THROTTLED 狀態下訂單 size 倍率 |
| `IdempotencyRule` | `ttl_seconds` | 300 | signal_id 去重 TTL（D6 凍結） |
| `IdempotencyRule` | `max_entries` | 100000 | LRU 快取上限 |
| `SignalFreshnessRule` | `max_age_seconds` | 30 | 訊號最大可接受年齡 |
| `SymbolWhitelistRule` | `symbols` | `[]` | 接受的 symbol 清單（空表示全部） |
| `PerOrderSizeCap` | `max_pct_of_equity` | 0.05 | 單筆訂單佔總權益上限 |
| `SymbolConcentrationCap` | `max_pct_of_equity` | 0.20 | 單一標的集中度上限 |
| `ThrottleScaler` | `scaler` | 0.5 | THROTTLED 縮量倍率（與 SystemStateRule 互補） |
| `PriceSanityCheck` | `max_deviation_pct` | 0.05 | 限價單偏離 last price 容忍度 |

## signal_ingestion.yaml — 訊號入口配置

完整 schema 由 `signals.config.SignalIngestionConfig` 定義。

### `tradingview` — TV Webhook adapter 配置

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `tradingview.secret` | str | — | URL secret token；最少 8 字元；**部署時改強隨機值，不入 git** |
| `tradingview.allowed_ips` | list[str] | TV 4 IP | 允許的 client IP；空清單代表全部接受（測試模式） |

### `dedupe` — 訊號去重配置

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `dedupe.ttl_seconds` | int | 300 | 5 分鐘 TTL（與 risk-gate IdempotencyRule 一致） |
| `dedupe.max_entries` | int | 100000 | LRU 快取上限 |

### `webhook` — Webhook 服務配置

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `webhook.rate_limit_per_second` | int | 10 | 每 IP 每秒上限（預留欄位，本 capability 未強制 enforce；建議由 reverse proxy 處理） |

### `scanner` — VibeShadowScannerAdapter 配置

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `scanner.schedule` | str | `"0 0 * * *"` | cron expression（stub 不使用，後續 change 啟用） |

## 變更生效步驟

1. 修改 `config/risk.yaml`
2. 執行單元測試確認 schema 仍合法：`pytest tests/test_config.py`
3. 重啟 vibe-auto-trader 服務
4. 啟動日誌會包含 `params_hash`（SHA-256），確認部署版本與預期一致

## 配置稽核

每筆 Decision 的 `reasons` 帶 `metadata`，包含當時生效的規則參數摘要。
透過 SQLite event log（後續 change）可重建任一時刻的配置快照。
