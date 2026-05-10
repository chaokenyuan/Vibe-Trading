# risk/rules/ — 11 條規則對照表

每條規則為獨立檔案／類別，皆實作 `RiskRule` Protocol。
執行順序由 `config/risk.yaml` 的 `rules.enabled` 清單控制（顯式 > 隱式）。

## 規則狀態總覽

| # | 規則名 | 類別 | 狀態 | 檔案位置 | 後續 change |
|---|--------|------|------|----------|------------|
| 1 | `SystemStateRule` | reject + clamp | **已實作** | `system_state.py` | — |
| 2 | `IdempotencyRule` | reject | **已實作** | `idempotency.py` | — |
| 3 | `SignalFreshnessRule` | reject | stub | `_stubs.py` | TBD |
| 4 | `SymbolWhitelistRule` | reject | stub | `_stubs.py` | TBD |
| 5 | `StrategyPausedRule` | reject | stub | `_stubs.py` | 需 strategy-host capability |
| 6 | `PerOrderSizeCap` | clamp | stub | `_stubs.py` | TBD |
| 7 | `StrategyBudgetCap` | clamp | stub | `_stubs.py` | 與 ledger 整合 |
| 8 | `SymbolConcentrationCap` | clamp | stub | `_stubs.py` | TBD |
| 9 | `ThrottleScaler` | clamp | stub | `_stubs.py` | 與 SystemStateRule 互補 |
| 10 | `PriceSanityCheck` | reject | stub | `_stubs.py` | 需即時 last price |
| 11 | `CapitalReservationRule` | reject | stub | `_stubs.py` | 包裝 `CapitalReserver.reserve` |

## 已實作規則細節

### `SystemStateRule`

訂閱 `StateChanged` 事件，依 FSM 當前狀態驅動。

| FSM 狀態 | Outcome | 行為 |
|---------|---------|------|
| NORMAL / WARNING | PASS | 不修改 |
| THROTTLED | CLAMP | size × `throttled_size_scaler`（預設 0.5） |
| HALTED / KILL_SWITCH / MAINTENANCE | REJECT | message 含當前狀態名 |

啟動時主動同步查 `StateMachine.state` 取初始狀態，之後靠事件更新。

### `IdempotencyRule`

以 `signal_id` 為主鍵的 5 分鐘 TTL 去重快取（D6 凍結）。

- 首次出現 → PASS，寫入快取
- TTL 內第二次 → REJECT，message 含 `age_seconds`
- TTL 後出現 → 視為新訊號，PASS 並覆寫快取
- 達 `max_entries`（預設 100,000）→ LRU 淘汰最早條目

TTL 計算使用 `clock.monotonic()`，與 wall-clock 解耦避免時鐘調整誤刪。

## 未實作規則的契約

每條 stub 規則的 `evaluate(ctx)` 拋 `NotImplementedError`，但類別簽名與 docstring 完整定義（用途／入參／出參／配置／實作策略），讓後續 change 直接填入邏輯即可，不需修改 RuleEngine 與 base.py。

## 規則開發流程

詳見 `risk/README.md` 的「擴充新規則的 SOP」一節。

## 對應 spec

`openspec/specs/risk-gate/spec.md` 的：

- Requirement「規則引擎採短路評估」
- Requirement「SystemStateRule 依 FSM 狀態決定門檻」
- Requirement「IdempotencyRule 以 signal_id 為主鍵 5 分鐘 TTL 去重」
- Requirement「未實作規則須提供契約 stub」
