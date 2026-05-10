## Why

`add-risk-gate` 凍結了 11 條規則的契約但僅實作 2 條（SystemStateRule、IdempotencyRule）；其餘 9 條為 stub（呼叫即拋 NotImplementedError）。本 change 把全部 9 條規則填入真實邏輯，使風控閘進入功能完整狀態。

## What Changes

替換 `risk/rules/_stubs.py` 為各別實作檔（每條規則一個檔）：

| 規則 | 類別 | 行為 | 依賴 |
|------|------|------|------|
| SignalFreshnessRule | reject | 訊號年齡 > max_age_seconds → REJECT | clock + config |
| SymbolWhitelistRule | reject | 空清單接受全部；非空僅接受清單內 symbol | config |
| StrategyPausedRule | reject | strategy state ≠ ACTIVE → REJECT | StrategyStateReader Protocol |
| PerOrderSizeCap | clamp | size 上限 = (max_pct × equity) / price | EquityReader Protocol |
| StrategyBudgetCap | clamp | size 上限依 ledger.strategy_available 推算 | ReservationLedgerReader Protocol |
| SymbolConcentrationCap | clamp | size 上限依 ledger.symbol_available 推算 | ReservationLedgerReader Protocol |
| ThrottleScaler | clamp | 預設 no-op（與 SystemStateRule 互補；未來可動態 scaler） | publisher（訂閱 StateChanged） |
| PriceSanityCheck | reject | 限價偏離 last 超過 max_deviation_pct → REJECT | market_data |
| CapitalReservationRule | reject + reservation | 呼叫 reserver.reserve；成功將 reservation_id 寫入 metadata | CapitalReserver |

新增 ports：

- `risk.ports.StrategyStateReader`：唯讀策略狀態查詢
- `risk.ports.EquityReader`：取總權益
- `risk.ports.ReservationLedgerReader`：唯讀 ledger 三道可用額度

修改：

- `risk/engine.py`：規則執行完畢後從最後一條規則 RuleVerdict.metadata 抽 `reservation_id` 寫入 Decision
- `risk/gate.py::_build_rules`：注入 9 條規則所需依賴
- 移除 `risk/rules/_stubs.py` 與 `tests/test_rule_stubs.py`（全規則已實作）

### 範圍外

- 規則熱載入（重啟才換，已凍結）
- ML-based dynamic thresholds（後續 change 視需求）
- 多市場規則差異化（如 A 股 T+1、加密 24/7）

## Capabilities

### Modified Capabilities

- `risk-gate`：原「未實作規則須提供契約 stub」requirement 移除（REMOVED），新增 9 個規則各自的行為 requirement

### New Capabilities

無（沿用 risk-gate 命名空間）。

## Impact

新增程式碼（一個檔一條規則）：

```
risk/rules/
├── freshness.py            SignalFreshnessRule
├── whitelist.py            SymbolWhitelistRule
├── strategy_paused.py      StrategyPausedRule
├── per_order_size_cap.py   PerOrderSizeCap
├── strategy_budget_cap.py  StrategyBudgetCap
├── symbol_concentration_cap.py  SymbolConcentrationCap
├── throttle_scaler.py      ThrottleScaler
├── price_sanity_check.py   PriceSanityCheck
└── capital_reservation.py  CapitalReservationRule
```

刪除：

- `risk/rules/_stubs.py`
- `tests/test_rule_stubs.py`

修改：

- `risk/ports.py`：加 3 個新 Protocol
- `risk/engine.py`：metadata 抽 reservation_id
- `risk/gate.py`：規則注入

依賴：無新外部依賴。
