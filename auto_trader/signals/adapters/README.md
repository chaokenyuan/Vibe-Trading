# signals/adapters/ — 4 個 SignalSource 對照表

| # | Adapter | 路徑 | 訊號級別 | 狀態 | 檔案 |
|---|---------|------|---------|------|------|
| 1 | `TradingViewWebhookAdapter` | TV Pine alert → FastAPI POST | 真實市場 | **已實作** | `tradingview.py` |
| 2 | `ManualCliAdapter` | 程式直接餵 Signal | 測試／補單 | **已實作** | `manual_cli.py` |
| 3 | `VibeShadowScannerAdapter` | Vibe-Trading scan_shadow_signals 拉取 | 研究級候選 | stub | `stubs.py` |
| 4 | `Mt5HttpPushAdapter` | 自寫 MT5 EA 透過 HTTP 推送 | 真實市場（FX） | stub | `stubs.py` |

所有 adapter 結構性符合 `SignalSource` Protocol（`async start/stop`）。

## 已實作 adapter 細節

### TradingViewWebhookAdapter

提供 `parse_payload(raw_dict) -> dict` 解析 TV alert message JSON 為 ingest 參數。
配對 `create_tradingview_app(adapter, router, config) -> FastAPI` factory 提供 webhook 路由。

```
POST /webhook/tv/{secret}/{strategy_id}
```

認證：URL secret + IP 白名單（雙因素）。
失敗回應：401（auth）/ 422（payload）/ 200（success）。

### ManualCliAdapter

直接接受 `Signal` 物件並推進 router。`source` 必須為 `manual`。
不啟動長期 process；外部 CLI 工具呼叫後即退出。

## Stub adapter

兩個 stub 各自 docstring 完整描述：用途／輸入／輸出／配置／預期實作策略。
呼叫 `start()` / `stop()` 即拋 `NotImplementedError`，附訊息指向後續 change。

後續 change 可直接填入內部邏輯，無需修改 SignalRouter 與 ports.py。

## 共用工具

- `signals/auth.py` — URL secret constant-time 比對 + IP 白名單檢查（適用所有 HTTP-based adapter）
- `signals/router.py::SignalRouter.ingest(...)` — 所有 adapter 的最終出口
