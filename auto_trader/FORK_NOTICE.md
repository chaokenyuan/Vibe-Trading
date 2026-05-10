# auto_trader — Fork-Specific Subsystem

本目錄是 **chaokenyuan/Vibe-Trading fork 專屬**，不在 HKUDS 上游中。

## 定位

Vibe-Trading 上游負責：研究、回測、訊號代碼導出（Pine/MQL5/TDX）。

`auto_trader/` 補上**自動下單執行層**：

```
   Vibe-Trading（上游）        auto_trader/（本子系統）
   ────────────────            ──────────────────────────
   策略研發                    訊號接收（webhook + Vibe scan）
   回測 / 統計驗證             多策略並行運行
   Pine/MQL5/TDX 導出          風險控制（FSM + 11 規則）
                               訂單執行（CCXT adapter）
                               持倉對帳（LogicalBook）
                               觀察性（audit log + alert + dashboard）
```

## 結構

```
auto_trader/
├── risk/                  雙層風控閘（FSM + RuleEngine + CapitalReserver）
├── signals/               訊號入口層（4 SignalSource adapter）
├── strategies/            策略主機 + LogicalBook + StrategyRegistry
├── execution/             訂單執行（OrderSink + CCXT stub）
├── reconciliation/        Fill 對帳 + PositionReader
├── observability/         AuditLogWriter + AlertSink + Health + PnLCalculator
├── reservation_bridge/    自動釋放預留（client_order_id ↔ reservation_id）
├── tests/                 371 unit + integration tests
├── config/                YAML 配置（risk / signal / execution / observability）
├── static/                Dashboard + Settings UI（純 HTML/JS，Chart.js CDN）
├── scripts/               demo.py + run_server.py（uvicorn webhook server）
├── openspec/              全 8 個 capability 的 OpenSpec spec/change 紀錄
└── docs/                  探索成果與設計 brief
```

## Quickstart（本子系統）

```bash
cd auto_trader/
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 跑測試
mypy risk/ signals/ strategies/ execution/ reconciliation/ \
     observability/ reservation_bridge/ tests/
pytest -q
ruff check .

# 一鍵端到端 demo（不需真交易所）
python scripts/demo.py

# 啟 webhook server + dashboard UI
export VIBE_TV_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"
python scripts/run_server.py
# 瀏覽器：http://localhost:8000/  (Dashboard)
#         http://localhost:8000/settings  (Settings)
```

## 測試覆蓋

- 371 tests passing（pytest -q）
- 121 source files mypy strict 0 errors
- ruff 0 errors

## 8 個 OpenSpec change（全 archived）

| change | 狀態 | spec |
|--------|------|------|
| add-risk-gate | archived | openspec/specs/risk-gate/ |
| add-signal-ingestion | archived | openspec/specs/signal-ingestion/ |
| add-strategy-host | archived | openspec/specs/strategy-host/ |
| add-order-execution | archived | openspec/specs/order-execution/ |
| add-reconciliation | archived | openspec/specs/reconciliation/ |
| add-observability | archived | openspec/specs/observability/ |
| add-reservation-release-bridge | archived | openspec/specs/reservation-release/ |
| add-risk-rules-impl | archived | （MODIFIED risk-gate） |

## 與上游的整合方式

- 訊號來源 1：TradingView webhook（從 Vibe-Trading 導出的 Pine Script alert）
- 訊號來源 2：`signals/adapters/stubs.py::VibeShadowScannerAdapter`
  將呼叫 `agent/src/shadow_account/scanner.py::scan_today_signals`（後續 change 連線）
- 對帳：未來與 `agent/src/shadow_account/backtester.py` 對照成交（後續 change）

## 來源

從 chaokenyuan/vibe-auto-trader（獨立 sister repo）migrate 而來。
原始 commit 歷史保留在該 repo（共 23 個 commit）；本目錄為打包遷移後的 snapshot。
