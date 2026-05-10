# auto_trader/

> Vibe-Trading fork 的自動下單子系統。
> 上游 Vibe-Trading 負責研究 / 回測 / 訊號代碼導出；本子系統補上訊號接收 + 風控 + 下單 + 對帳 + 監控。

## 一頁 Quickstart

```bash
cd auto_trader/
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 跑全測試
pytest -q                                   # 371 tests
mypy risk/ signals/ strategies/ execution/ \
     reconciliation/ observability/ reservation_bridge/ tests/   # 121 files
ruff check .                                # clean

# 端到端 demo（不需真交易所）
python scripts/demo.py

# 啟動 webhook server + Dashboard / Settings UI
export VIBE_TV_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"
python scripts/run_server.py
# 瀏覽器：
#   http://localhost:8000/         （Dashboard：FSM / ledger / PnL / equity 曲線 / K 線）
#   http://localhost:8000/settings （Settings：reset / maintenance / 策略管理 / 模擬訊號）
```

## 架構（8 個 capability）

```
   TradingView Pine alert / Vibe scan
       │
       ▼
   ┌──────────────────────────────────────────────────┐
   │ signals/             訊號入口（4 SignalSource）    │
   │   • TradingViewWebhookAdapter（完整實作）         │
   │   • ManualCliAdapter                             │
   │   • VibeShadowScannerAdapter（stub，待整合上游）   │
   │   • Mt5HttpPushAdapter（stub）                    │
   │   • SignalDedupe（5 min TTL）                     │
   └──────────┬───────────────────────────────────────┘
              ▼
   ┌──────────────────────────────────────────────────┐
   │ strategies/          策略主機 + LogicalBook       │
   │   • Strategy Protocol、StrategyRegistry          │
   │   • PassthroughStrategy（示範）                   │
   │   • client_order_id 編碼（追蹤回 strategy）       │
   └──────────┬───────────────────────────────────────┘
              ▼
   ┌──────────────────────────────────────────────────┐
   │ risk/                雙層風控閘                    │
   │   Layer 1：FSM（NORMAL/WARNING/THROTTLED/         │
   │            HALTED/KILL_SWITCH/MAINTENANCE）      │
   │   Layer 2：11 條規則（短路 + clamp）               │
   │   CapitalReserver actor（asyncio.Queue）          │
   └──────────┬───────────────────────────────────────┘
              ▼
   ┌──────────────────────────────────────────────────┐
   │ execution/           訂單執行                      │
   │   • OrderSink Protocol                           │
   │   • ExchangeOrderSink + MockExecutionAdapter     │
   │   • CcxtExecutionAdapter（stub）                  │
   └──────────┬───────────────────────────────────────┘
              ▼ broker fills
   ┌──────────────────────────────────────────────────┐
   │ reconciliation/      Fill 對帳                    │
   │   • FillProcessor → LogicalBook.apply_fill        │
   │   • BrokerPositionTracker（派生視圖）              │
   │   • BookPositionReader（給 risk-gate 用）         │
   └──────────────────────────────────────────────────┘

   ┌──────────────────────────────────────────────────┐
   │ reservation_bridge/  自動釋放預留                  │
   │   client_order_id ↔ reservation_id mapping       │
   │   reject / fill 即釋放                            │
   └──────────────────────────────────────────────────┘

   ┌──────────────────────────────────────────────────┐
   │ observability/       稽核 + 告警 + 健康            │
   │   • AuditLogWriter（JSON Lines）                  │
   │   • AlertSink（LoggingAlertSink + Telegram stub） │
   │   • PnLCalculator（unrealized + realized）        │
   │   • create_health_app（FastAPI /health /readyz）  │
   └──────────────────────────────────────────────────┘
```

## 目錄

| 路徑 | 內容 |
|------|------|
| `risk/` | 雙層風控閘 + 11 規則實作 |
| `signals/` | 訊號入口 + 4 adapter |
| `strategies/` | Strategy + LogicalBook + Registry |
| `execution/` | OrderSink + MockBroker + Ccxt stub |
| `reconciliation/` | FillProcessor + PositionReader |
| `observability/` | Audit + AlertSink + PnL + Health |
| `reservation_bridge/` | 預留自動釋放 |
| `tests/` | 371 tests（unit + integration + e2e） |
| `config/` | 4 個 YAML（risk / signal / execution / observability） |
| `static/` | Dashboard + Settings UI（HTML/JS + Chart.js） |
| `scripts/` | `demo.py` + `run_server.py` |
| `openspec/` | 8 個 archived change（spec / design / tasks） |
| `docs/` | 探索 design-brief（含 Vibe-Trading 訊號介面修訂紀錄） |

## OpenSpec 規格驅動歷程

8 個 archived change（每個都跑完 explore → propose → design → specs → tasks → apply → verify → archive）：

```
   add-risk-gate                  88 task / 14 SHALL / 41 scenarios
   add-signal-ingestion           13 ch / 11 SHALL
   add-strategy-host              9 ch
   add-order-execution            8 ch
   add-reconciliation             5 ch
   add-observability              6 ch
   add-reservation-release-bridge 4 ch
   add-risk-rules-impl            REMOVED stubs + 9 ADDED rules
```

詳見 `openspec/specs/`（main specs）與 `openspec/changes/archive/`（每個 change 的完整 audit）。

## 與上游 Vibe-Trading 的整合方式

### 訊號路徑（生產）

1. Vibe-Trading 用 LLM agent 研發策略 → 導出 Pine Script
2. 在 TradingView 部署 Pine Script + 設 alert webhook
3. Webhook 打 auto_trader 的 `/webhook/tv/{secret}/{strategy_id}`
4. auto_trader 跑完整鏈路：去重 → 風控 → 下單 → 對帳

### 訊號路徑（研究級候選）

1. `agent/src/shadow_account/scanner.py::scan_today_signals` 產候選清單
2. `signals/adapters/stubs.py::VibeShadowScannerAdapter`（待整合）
   定時拉取候選 → 推 SignalRouter
3. 候選等級訊號建議搭配人工複核 + 加重風控

## 後續路線圖

- [ ] PnL chart 完整 wiring（dashboard.html，Chart.js 已加但需驗證真實資料）
- [ ] VibeShadowScannerAdapter 真實實作（連 `agent/src/shadow_account/scanner.py`）
- [ ] CcxtExecutionAdapter（Binance Testnet）
- [ ] CcxtFillSource（WebSocket fill stream）
- [ ] TelegramAlertSink 真實版

## License

MIT（與上游 Vibe-Trading 一致）。

## 相關

- 上游：[HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading)
- 來源 repo：[chaokenyuan/vibe-auto-trader](https://github.com/chaokenyuan/vibe-auto-trader)（snapshot；後續開發在本 fork）
- Migration 紀錄：見 `FORK_NOTICE.md`
