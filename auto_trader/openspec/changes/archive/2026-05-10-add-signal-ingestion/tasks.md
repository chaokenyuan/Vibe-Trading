## 1. 專案骨架與依賴

- [x] 1.1 建立 `signal/` 套件目錄與 `signal/adapters/` 子模組 `__init__.py`
- [x] 1.2 建立 `config/signal_ingestion.yaml` 預設範本（含預設 TV IP，secret 留 placeholder）
- [x] 1.3 在 `pyproject.toml` 新增依賴：`fastapi>=0.110`、`uvicorn[standard]>=0.27`、`httpx>=0.27`
- [x] 1.4 確認既有 mypy strict / ruff / pytest 配置覆蓋 `signal/` 與測試

## 2. 值物件與型別定義

- [x] 2.1 在 `signal/types.py` 定義 `SignalSourceKind` StrEnum（tradingview / mt5 / vibe_shadow / manual）
- [x] 2.2 在 `signal/types.py` 定義 `Signal` frozen dataclass（含 schema_version=1、所有 spec 欄位）
- [x] 2.3 在 `signal/types.py` 定義 `StrategyMetadata` frozen dataclass（strategy_id / strategy_version / params_hash）
- [x] 2.4 實作 `Signal.to_dict()` 序列化（共用 risk._serialize.to_json_safe）
- [x] 2.5 撰寫 Signal / StrategyMetadata 不可變性與序列化測試

## 3. Ports（DIP 邊界）

- [x] 3.1 在 `signal/ports.py` 定義 `SignalSource` Protocol（async start/stop, runtime_checkable）
- [x] 3.2 在 `signal/ports.py` 定義 `SignalConsumer` Protocol（async on_signal）
- [x] 3.3 在 `signal/ports.py` 定義 `StrategyRegistryProtocol`（get_strategy_metadata）
- [x] 3.4 撰寫 ports 結構驗證測試（runtime_checkable + isinstance）

## 4. 配置模型

- [x] 4.1 在 `signal/config.py` 定義 pydantic 模型：`TradingViewConfig`、`DedupeConfig`、`WebhookConfig`、`ScannerConfig`、`SignalIngestionConfig`
- [x] 4.2 實作 `SignalIngestionConfig.from_yaml(path)` 與啟動驗證
- [x] 4.3 預設 allowed_ips 為 TV 4 個官方 IP（52.89.214.238 / 34.212.75.30 / 54.218.53.128 / 52.32.178.7）
- [x] 4.4 撰寫測試：合法配置 / 缺 secret / 預設 IP

## 5. SignalDedupe

- [x] 5.1 在 `signal/dedupe.py` 實作 `SignalDedupe`：OrderedDict-based LRU + clock.monotonic TTL
- [x] 5.2 對外 API：`is_duplicate(signal_id) -> bool`、`size` property
- [x] 5.3 撰寫測試：首次通過、TTL 內重複、TTL 後不重複、LRU 淘汰

## 6. StrategyRegistry stub

- [x] 6.1 在 `signal/registry_stub.py` 實作 `InMemoryStrategyRegistry`：`register(metadata)`、`get_strategy_metadata(id)`
- [x] 6.2 撰寫測試：已註冊回傳 metadata、未註冊回傳 None

## 7. SignalRouter

- [x] 7.1 在 `signal/router.py` 實作 `SignalRouter`：
  - 註冊 SignalConsumer（subscribe API）
  - async ingest(raw_payload, source: SignalSourceKind) → 補 metadata + signal_id 計算 + dedupe + fan-out
  - async start/stop 啟動所有註冊的 SignalSource
- [x] 7.2 實作 signal_id 計算（sha256 of strategy_id|symbol|side|bar_time|interval）
- [x] 7.3 實作 metadata 補齊：未知 strategy_id 拒絕並記錄
- [x] 7.4 實作 fan-out 故障隔離（任一 consumer 失敗不影響其他）
- [x] 7.5 撰寫單元測試覆蓋 spec scenario：
  - 多 consumer fan-out
  - 一 consumer 失敗其他繼續
  - TTL 內重送被去重
  - TTL 後重送視為新訊號
  - 未知 strategy_id 拒絕
  - signal_id 計算確定性
  - received_at 不影響 signal_id

## 8. TradingViewWebhookAdapter

- [x] 8.1 在 `signal/auth.py` 實作 `verify_secret(provided, expected)` constant-time + `verify_ip(client_ip, allowed_ips)` 白名單檢查
- [x] 8.2 在 `signal/adapters/tradingview.py` 實作 `TradingViewWebhookAdapter`：
  - async start() / stop() 為 no-op（FastAPI app 由 factory 提供）
  - parse_payload(raw_dict) → Signal（schema_version 檢查、必填欄位驗證、Decimal 解析）
- [x] 8.3 提供 `create_tradingview_app(adapter, router, config) -> FastAPI` factory：
  - 註冊 POST /webhook/tv/{secret}/{strategy_id} 路由
  - 認證流程：URL secret + IP 白名單 + JSON 解析
  - 失敗回應：401（auth）/ 422（payload）/ 200（success）
- [x] 8.4 撰寫測試（使用 `httpx.ASGITransport` 直接打 app，不啟動 uvicorn）：
  - secret 正確 + IP 白名單 → 200
  - secret 錯誤 → 401
  - IP 不白名單 → 401
  - 空 allowed_ips（測試模式）接受全部
  - 無效 JSON → 422
  - 缺欄位 → 422
  - schema_version 不為 1 → 422
  - 完整流程：webhook → router → consumer 收到 Signal

## 9. ManualCliAdapter

- [x] 9.1 在 `signal/adapters/manual_cli.py` 實作 `ManualCliAdapter`：
  - async start/stop 為 no-op
  - async submit(signal: Signal) → 推進 router；source != "manual" 則 raise ValueError
- [x] 9.2 撰寫測試：成功 submit、source 不為 manual 拒絕

## 10. Stub adapters（VibeShadow + MT5）

- [x] 10.1 在 `signal/adapters/stubs.py` 實作 `VibeShadowScannerAdapter` stub：start() 拋 NotImplementedError
- [x] 10.2 同檔實作 `Mt5HttpPushAdapter` stub
- [x] 10.3 兩 stub 含完整 docstring（用途／輸入／輸出／配置／實作策略）
- [x] 10.4 撰寫測試：stub start() 拋 NotImplementedError、結構符合 SignalSource Protocol

## 11. 整合測試

- [x] 11.1 撰寫 e2e 測試：FastAPI app + InMemoryStrategyRegistry + InMemoryConsumer，模擬 TV webhook 完整流程
- [x] 11.2 撰寫並發測試：100 個 webhook 請求 asyncio.gather，驗證 dedupe 與 fan-out 一致
- [x] 11.3 撰寫測試：未知 strategy_id 的 webhook 收 200 但不分發給 consumer（router 內部拒）
- [x] 11.4 撰寫測試：ManualCliAdapter + TradingViewWebhookAdapter 並用，相同 signal_id 跨 source 觸發 dedupe

## 12. 文件

- [x] 12.1 在 `signal/README.md` 撰寫模組說明：架構、入口、4 條訊號路徑
- [x] 12.2 在 `signal/adapters/README.md` 列 4 個 adapter 對照表（已實作 / stub）
- [x] 12.3 補 `config/README.md` 增加 signal_ingestion.yaml 區段
- [x] 12.4 更新 README.md 進度表（add-signal-ingestion 完成標記）

## 13. 驗收

- [x] 13.1 執行 `openspec validate add-signal-ingestion` 通過
- [x] 13.2 全部 spec scenario 對應到測試
- [x] 13.3 `mypy --strict signal/ tests/` 零錯誤
- [x] 13.4 `pytest --cov=signal` 覆蓋率 ≥ 90%
- [x] 13.5 撰寫 acceptance.md 含部署 checklist 與後續 change 預告
