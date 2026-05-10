# signal-ingestion capability

訊號入口層 — 把外部世界的訊號（TradingView Pine alert、Vibe-Trading scanner、人工 CLI、MT5 EA）轉換為內部正規化的 `Signal`，並交給下游 strategy-host 消費。

> **注意**：套件名為 `signals`（複數）以避開 Python stdlib 的 `signal` 模組衝突。

## 模組結構

```
signals/
├── __init__.py
├── types.py              Signal frozen dataclass + StrategyMetadata + SignalSourceKind enum
├── ports.py              SignalSource / SignalConsumer / StrategyRegistryProtocol
├── router.py             SignalRouter（編排器：補 metadata + dedupe + fan-out）
├── dedupe.py             SignalDedupe（LRU + TTL 快取）
├── config.py             pydantic SignalIngestionConfig
├── registry_stub.py      InMemoryStrategyRegistry（後續 strategy-host change 取代）
├── auth.py               URL secret + IP 白名單驗證
└── adapters/
    ├── tradingview.py    TradingViewWebhookAdapter + create_tradingview_app
    ├── manual_cli.py     ManualCliAdapter
    └── stubs.py          VibeShadowScannerAdapter + Mt5HttpPushAdapter（stub）
```

## 對外進入點

```python
from signals.adapters.manual_cli import ManualCliAdapter
from signals.adapters.tradingview import TradingViewWebhookAdapter, create_tradingview_app
from signals.config import SignalIngestionConfig
from signals.dedupe import SignalDedupe
from signals.registry_stub import InMemoryStrategyRegistry
from signals.router import SignalRouter
from risk.adapters.system_clock import SystemClock

# 1. 載入配置
config = SignalIngestionConfig.from_yaml("config/signal_ingestion.yaml")

# 2. 建構 SignalRouter
clock = SystemClock()
registry = InMemoryStrategyRegistry()  # 後續由 strategy-host 提供
dedupe = SignalDedupe(
    clock=clock,
    ttl_seconds=config.dedupe.ttl_seconds,
    max_entries=config.dedupe.max_entries,
)
router = SignalRouter(clock=clock, registry=registry, dedupe=dedupe)

# 3. 註冊下游 consumer（strategy-host 後續實作）
router.subscribe(strategy_host_consumer)

# 4. 啟動 source
tv_adapter = TradingViewWebhookAdapter()
router.attach_source(tv_adapter)
manual_adapter = ManualCliAdapter(router=router)
router.attach_source(manual_adapter)

await router.start()

# 5. TV webhook FastAPI app（由 deployment 層啟 uvicorn）
app = create_tradingview_app(adapter=tv_adapter, router=router, config=config.tradingview)
```

## 訊號路徑

```
   Source                  Adapter                    Status     觸發方式
   ─────────────────────   ─────────────────────────  ────────   ──────────────
   TradingView Pine alert  TradingViewWebhookAdapter  完整實作    HTTP POST webhook
   人工 / 開發測試          ManualCliAdapter           完整實作    程式直接 submit
   Vibe-Trading scanner    VibeShadowScannerAdapter   stub       Cron pull
   MT5 EA                  Mt5HttpPushAdapter         stub       HTTP push
```

四條路徑各有不同 trust level，由 SignalRouter 統一處理 metadata 補齊、去重、fan-out。

## 認證（TV Webhook）

- URL secret token：`/webhook/tv/{secret}/{strategy_id}`，constant-time 比對
- IP 白名單：預設 4 個 TradingView 官方 IP（可由 `config/signal_ingestion.yaml` 覆寫）
- 強制 https：由 reverse proxy（Cloudflare／Caddy）守，本 capability 不負責 TLS

## 訊號去重

`SignalDedupe` 以 `signal_id` 為主鍵的 LRU + TTL 快取：

- TTL 預設 300 秒（5 分鐘）
- 上限預設 100,000 筆，超出 LRU 淘汰
- TTL 計算使用 `clock.monotonic()`，與 wall-clock 解耦

`signal_id = sha256(strategy_id|symbol|side|bar_time|interval)`：跨 source 一致。

## 擴充新 SignalSource 的 SOP

1. 在 `signals/adapters/` 新增檔案，定義類別實作 `SignalSource` Protocol（`async start/stop`）
2. 內部以 `SignalRouter.ingest(...)` 推送訊號
3. 在 `SignalSourceKind` enum 加新值
4. 撰寫單元測試（使用 InMemoryStrategyRegistry + RecordingConsumer 即可）
5. 在 `config/signal_ingestion.yaml` 加區段（必要時）

## 設計原則

- **SOLID**：所有元件透過 `ports.py` 的 Protocol 互動
- **不可變性**：Signal、StrategyMetadata 為 frozen dataclass
- **可審計**：Signal 帶完整 `raw_payload` 與 `received_at`，可重放
- **時間抽象**：所有時間相依透過注入的 `Clock`
- **故障隔離**：fan-out 時任一 consumer 失敗不影響其他

## 已知限制（MVP）

- VibeShadowScannerAdapter 與 Mt5HttpPushAdapter 為 stub，呼叫 start() 即拋 NotImplementedError
- StrategyRegistry 為 in-memory stub；strategy-host change 將提供完整版本
- Webhook 速率限制設定於 config，但本 capability 未實作 enforcement（由 reverse proxy 守）
- 無持久化；服務重啟丟失去重快取

## 相關文件

- 需求規格：`openspec/specs/signal-ingestion/spec.md`
- 設計理由：`openspec/changes/add-signal-ingestion/design.md`
- 4 adapter 對照表：`signals/adapters/README.md`
- 配置：`config/README.md` 的 signal_ingestion.yaml 區段
