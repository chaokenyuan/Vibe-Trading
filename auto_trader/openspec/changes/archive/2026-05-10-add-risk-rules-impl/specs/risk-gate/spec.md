## REMOVED Requirements

### Requirement: 未實作規則須提供契約 stub

**Reason**: 全 9 條規則於 add-risk-rules-impl change 完整實作；不再有 stub 語意。

**Migration**: 移除 risk/rules/_stubs.py 與 tests/test_rule_stubs.py。各規則具體行為由本 change 新增的 requirements 定義（見 ADDED）。

---

## ADDED Requirements

### Requirement: SignalFreshnessRule 拒絕過舊訊號

`SignalFreshnessRule` SHALL 比較 `ctx.intent.bar_time` 與 `ctx.clock.now()` 的差距；超過 `max_age_seconds`（預設 30）SHALL 回 REJECT。

#### Scenario: 訊號在閾值內通過

- **WHEN** intent.bar_time 與 now() 相差 10 秒，max_age_seconds=30
- **THEN** SHALL 回 PASS

#### Scenario: 訊號超過閾值拒絕

- **WHEN** intent.bar_time 與 now() 相差 60 秒，max_age_seconds=30
- **THEN** SHALL 回 REJECT，message 含 age 與 threshold

---

### Requirement: SymbolWhitelistRule 限制可交易標的

`SymbolWhitelistRule` SHALL 依配置 `symbols: list[str]` 行為：

- 空清單：接受所有 symbol（PASS）
- 非空清單：僅接受清單內 symbol，否則 REJECT

#### Scenario: 空白名單接受全部

- **WHEN** symbols=[] 且 intent.symbol="BTCUSDT"
- **THEN** SHALL 回 PASS

#### Scenario: 在白名單通過

- **WHEN** symbols=["BTCUSDT","ETHUSDT"] 且 intent.symbol="BTCUSDT"
- **THEN** SHALL 回 PASS

#### Scenario: 不在白名單拒絕

- **WHEN** symbols=["BTCUSDT"] 且 intent.symbol="SOLUSDT"
- **THEN** SHALL 回 REJECT

---

### Requirement: StrategyPausedRule 拒絕非 ACTIVE 策略訊號

`StrategyPausedRule` SHALL 透過 `StrategyStateReader.get_state(strategy_id)` 查策略狀態：非 ACTIVE 即 REJECT；reader 找不到（None）也 REJECT。

#### Scenario: ACTIVE 通過

- **WHEN** state="ACTIVE"
- **THEN** SHALL 回 PASS

#### Scenario: PAUSED 拒絕

- **WHEN** state="PAUSED"
- **THEN** SHALL 回 REJECT

#### Scenario: 未知 strategy_id 拒絕

- **WHEN** reader.get_state 回 None
- **THEN** SHALL 回 REJECT

---

### Requirement: PerOrderSizeCap 限制單筆訂單佔總權益

`PerOrderSizeCap` SHALL 依配置 `max_pct_of_equity`（預設 0.05）與注入的 `EquityReader` 計算上限：

```
notional_cap = max_pct_of_equity × equity
qty_cap = notional_cap / price
clamped = min(current_size, qty_cap)
```

`price` 為 intent.price；intent.price 為 None 時使用 `market_data.get_last_price(symbol)`。

#### Scenario: 超過上限 CLAMP

- **WHEN** current_size=1000，equity=10000，max_pct=0.05，price=1（cap = 500 qty）
- **THEN** SHALL 回 CLAMP，after_value=500

#### Scenario: 在上限內 PASS

- **WHEN** current_size=100，equity=10000，max_pct=0.05，price=1（cap = 500）
- **THEN** SHALL 回 PASS

---

### Requirement: StrategyBudgetCap 限制策略累積金額

`StrategyBudgetCap` SHALL 依注入的 `ReservationLedgerReader.strategy_available(strategy_id)` 計算 max_qty 並 clamp。

#### Scenario: 策略額度不足 CLAMP

- **WHEN** strategy_available=500，price=10（max_qty=50），current_size=100
- **THEN** SHALL 回 CLAMP，after_value=50

---

### Requirement: SymbolConcentrationCap 限制單一標的曝險

`SymbolConcentrationCap` SHALL 依注入的 `ReservationLedgerReader.symbol_available(symbol)` 計算 max_qty 並 clamp。

#### Scenario: 標的集中度不足 CLAMP

- **WHEN** symbol_available=300，price=10（max_qty=30），current_size=100
- **THEN** SHALL 回 CLAMP，after_value=30

---

### Requirement: ThrottleScaler 預設 no-op

`ThrottleScaler` SHALL 預設 PASS（不修改 size）。配置 `scaler` < 1.0 且 FSM 為 THROTTLED 時可主動 CLAMP；MVP 保留為 no-op。

#### Scenario: 預設配置下 PASS

- **WHEN** scaler 預設值
- **THEN** SHALL 回 PASS，size 不變

---

### Requirement: PriceSanityCheck 拒絕偏離 last 過大的限價單

`PriceSanityCheck` SHALL 比對 intent.price 與 `market_data.get_last_price(symbol)`：

- intent.price 為 None（市價單）→ PASS
- abs(price - last) / last > max_deviation_pct（預設 0.05） → REJECT

#### Scenario: 市價單 PASS

- **WHEN** intent.price=None
- **THEN** SHALL 回 PASS

#### Scenario: 限價偏離合理範圍 PASS

- **WHEN** intent.price=65000, last=65500（偏離 0.76%），max=5%
- **THEN** SHALL 回 PASS

#### Scenario: 限價偏離過大 REJECT

- **WHEN** intent.price=70000, last=65000（偏離 7.7%），max=5%
- **THEN** SHALL 回 REJECT

---

### Requirement: CapitalReservationRule 預留資金並注入 reservation_id

`CapitalReservationRule` SHALL 透過注入的 `CapitalReserver`：

1. 計算 notional = current_size × (intent.price 或 market_data.last_price)
2. 呼叫 `await reserver.reserve(intent, notional)`
3. 成功 → PASS，metadata 含 `reservation_id` 字串
4. 失敗（ledger 三道任一不足）→ REJECT，message 含 reason

`RuleEngine` SHALL 在組 Decision 時，自最後一條 RuleVerdict.metadata 中抽 `reservation_id` 寫入 `Decision.reservation_id`（若存在）。

#### Scenario: 預留成功 metadata 含 reservation_id

- **WHEN** reserver.reserve 成功
- **THEN** RuleVerdict.outcome=PASS，metadata["reservation_id"] 為 UUID 字串

#### Scenario: 預留失敗 REJECT

- **WHEN** ledger 集中度不足
- **THEN** RuleVerdict.outcome=REJECT，message 含 reason

#### Scenario: Decision 抽 reservation_id

- **WHEN** 流程通過 CapitalReservationRule 並成功預留
- **THEN** Decision.reservation_id SHALL 與 metadata 中的值一致
