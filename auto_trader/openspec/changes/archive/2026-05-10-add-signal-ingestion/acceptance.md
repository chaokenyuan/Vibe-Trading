# add-signal-ingestion — 驗收紀錄

> 對應 task 13.1–13.5。本文件為 change archive 前的最終驗證快照。

## 13.1 OpenSpec 結構驗證

```
$ openspec validate add-signal-ingestion
Change 'add-signal-ingestion' is valid
```

artifacts 完整：`proposal.md` / `design.md` / `specs/signal-ingestion/spec.md` / `tasks.md`。

## 13.2 Spec scenario 對測試覆蓋對照

`spec.md` 共 11 條 SHALL requirement / 31 個 Given-When-Then scenario，全部對應到測試。

主要對照：

| Requirement | scenario | 覆蓋測試 |
|-------------|---------|---------|
| 訊號入口層提供 4 種 SignalSource | TV/Manual 完整實作 | `test_signal_tradingview.py::*`, `test_signal_manual_cli.py::test_submit_with_manual_source_succeeds` |
| 訊號入口層提供 4 種 SignalSource | Vibe Shadow / MT5 為 stub | `test_signal_stubs.py::test_stub_start_raises_not_implemented` |
| 訊號入口層提供 4 種 SignalSource | 4 adapter 滿足 SignalSource Protocol | `test_signal_stubs.py::test_stub_satisfies_signal_source_protocol`, `test_signal_ports.py` |
| Signal 為不可變正規化值物件 | signal_id 確定計算 | `test_signal_router.py::test_signal_id_deterministic` |
| Signal 為不可變正規化值物件 | received_at 不影響 signal_id | `test_signal_router.py::test_signal_id_deterministic` |
| Signal 為不可變正規化值物件 | 不可變 | `test_signal_types.py::test_signal_immutable` |
| Signal 為不可變正規化值物件 | JSON 序列化 | `test_signal_types.py::test_signal_to_dict_json_serializable` |
| SignalRouter 集中處理去重與下游分發 | 多 consumer fan-out | `test_signal_router.py::test_multiple_consumers_all_receive` |
| SignalRouter 集中處理去重與下游分發 | 一 consumer 失敗其他繼續 | `test_signal_router.py::test_failing_consumer_does_not_break_others` |
| SignalRouter 集中處理去重與下游分發 | TTL 內重送被去重 | `test_signal_router.py::test_duplicate_within_ttl_not_dispatched` |
| SignalRouter 集中處理去重與下游分發 | TTL 後視為新訊號 | `test_signal_router.py::test_after_ttl_dispatched_again` |
| SignalRouter 集中處理去重與下游分發 | 未知 strategy_id 拒 | `test_signal_router.py::test_ingest_unknown_strategy_rejected`, `test_signal_integration.py::test_webhook_unknown_strategy_id_returns_200_but_no_dispatch` |
| TradingView 認證雙因素 | secret 正確 + IP 白名單 200 | `test_signal_tradingview.py::test_correct_secret_and_allowed_ip_accepted` |
| TradingView 認證雙因素 | secret 錯 401 | `test_signal_tradingview.py::test_wrong_secret_returns_401` |
| TradingView 認證雙因素 | IP 不白名單 401 | `test_signal_tradingview.py::test_ip_not_in_whitelist_returns_401` |
| TradingView 認證雙因素 | 空白名單接受全部 | `test_signal_tradingview.py::test_empty_allowed_ips_accepts_all` |
| TradingView 認證雙因素 | 無效 JSON 422 | `test_signal_tradingview.py::test_invalid_json_returns_422` |
| TV alert message 解析 | 標準 payload 解析成功 | `test_signal_tradingview.py::test_parse_payload_valid` |
| TV alert message 解析 | 缺欄位 422 | `test_signal_tradingview.py::test_missing_field_returns_422` |
| TV alert message 解析 | schema_version 不為 1 拒 | `test_signal_tradingview.py::test_unsupported_schema_version_returns_422` |
| ManualCliAdapter | 直接 submit 成功 | `test_signal_manual_cli.py::test_submit_with_manual_source_succeeds` |
| ManualCliAdapter | source 不為 manual 拒 | `test_signal_manual_cli.py::test_submit_with_non_manual_source_raises` |
| SignalDedupe | 首次通過 | `test_signal_dedupe.py::test_first_signal_id_not_duplicate` |
| SignalDedupe | TTL 內重複 | `test_signal_dedupe.py::test_repeat_within_ttl_is_duplicate` |
| SignalDedupe | TTL 過期不重複 | `test_signal_dedupe.py::test_after_ttl_not_duplicate_and_overwrite` |
| SignalDedupe | LRU 淘汰 | `test_signal_dedupe.py::test_lru_eviction_when_over_max_entries` |
| 配置 YAML 驗證 | 合法載入成功 | `test_signal_config.py::test_default_yaml_loads`, `test_minimal_valid_config` |
| 配置 YAML 驗證 | 缺 secret 阻止 | `test_signal_config.py::test_missing_secret_raises` |
| 配置 YAML 驗證 | 預設 IP | `test_signal_config.py::test_default_allowed_ips_uses_tv_official` |
| StrategyRegistry stub | 已註冊回 metadata | `test_signal_registry_stub.py::test_registered_strategy_returns_metadata` |
| StrategyRegistry stub | 未註冊回 None | `test_signal_registry_stub.py::test_unknown_strategy_returns_none` |
| Clock Protocol 注入 | FrozenClock 控制 TTL | `test_signal_dedupe.py::test_repeat_within_ttl_is_duplicate`, `test_after_ttl_not_duplicate_and_overwrite` |
| SignalRouter lifecycle | start 啟動所有 source | `test_signal_router.py::test_start_starts_all_sources` |
| SignalRouter lifecycle | 重複 start 拋 | `test_signal_router.py::test_double_start_raises` |
| SignalRouter lifecycle | stop 冪等 | `test_signal_router.py::test_stop_idempotent` |

## 13.3 Mypy 嚴格模式

```
$ mypy risk/ signals/ tests/
Success: no issues found in 68 source files
```

## 13.4 測試覆蓋率

```
$ pytest --cov=signals --cov=risk -q
TOTAL  1105 lines  22 missed  98%
304 passed
```

`signals/` 模組覆蓋率：

| 模組 | 覆蓋率 |
|------|-------|
| `signals/__init__.py` | 100% |
| `signals/types.py` | 100% |
| `signals/ports.py` | 100% |
| `signals/config.py` | 100% |
| `signals/dedupe.py` | 100% |
| `signals/registry_stub.py` | 100% |
| `signals/router.py` | 100% |
| `signals/auth.py` | 100% |
| `signals/adapters/manual_cli.py` | 100% |
| `signals/adapters/stubs.py` | 100% |
| `signals/adapters/tradingview.py` | 94% |

整體含 risk/ 一起 **98%**，> 90% 目標。

## 13.5 部署 Checklist 與已知限制

### MVP 限制（後續 change 處理）

| 項目 | 限制 | 後續 change |
|------|------|------------|
| StrategyRegistry | InMemoryStrategyRegistry，無持久化 | `add-strategy-host` 取代 |
| SignalConsumer | 無生產實作，需 strategy-host 提供 | `add-strategy-host` |
| VibeShadowScannerAdapter | stub，未實作 cron pull | 後續獨立 change |
| Mt5HttpPushAdapter | stub，未實作 EA 接收端 | 後續獨立 change |
| Webhook 速率限制 | config 有欄位但本 capability 未 enforce | 由 reverse proxy 守 |
| 訊號審計持久化 | EventPublisher 廣播未連接 SQLite | `add-sqlite-event-log` |

### 部署前驗證 checklist

- [ ] `openspec validate add-signal-ingestion` 通過
- [ ] `mypy --strict signals/ tests/` 通過
- [ ] `pytest -x` 通過
- [ ] `ruff check signals/ tests/` 通過
- [ ] `pytest --cov=signals` ≥ 90%
- [ ] `config/signal_ingestion.yaml` 的 `tradingview.secret` 已從 placeholder 改為強隨機值
- [ ] `tradingview.allowed_ips` 與 TV 當前公開 IP 列表一致
- [ ] secret 未入 git（.gitignore 或從 env var 注入）
- [ ] reverse proxy（如 Cloudflare／Caddy）已設置 TLS 終止與速率限制
- [ ] InMemoryStrategyRegistry 已預先註冊所有上線策略

### 後續 change 預告

下一個建議的 change：

1. **`add-strategy-host`**：實作 LogicalBook + Strategy lifecycle + 完整 StrategyRegistry，提供真正的 SignalConsumer
2. **`add-sqlite-event-log`**：將 risk + signal 的 EventPublisher 廣播持久化至 SQLite
3. **`add-vibe-shadow-scanner`**：填補 VibeShadowScannerAdapter 的 cron pull 邏輯
