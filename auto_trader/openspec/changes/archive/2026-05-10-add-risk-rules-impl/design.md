## Context

9 條規則之中，3 條僅依賴 RuleContext（freshness / whitelist / price sanity），6 條需要額外注入。為避免 RuleContext 膨脹（已有 8 個欄位），各規則的特殊依賴透過 `__init__` 注入；engine 透過 `gate._build_rules` 統一裝配。

## Goals

1. 全部 9 條規則完整實作，邊界明確
2. 不擴大 RuleContext；新依賴用 Protocol + 構造注入
3. CapitalReservationRule 的 reservation_id 透過 metadata 傳出（engine 抽取）
4. 既有 system_state / idempotency 規則行為不變

## Decisions

### D-1：新依賴用 Protocol，避免具體類耦合

新增三個 Protocol（皆 read-only）：

- `StrategyStateReader.get_state(strategy_id) -> str | None`
- `EquityReader.get_total_equity() -> Decimal`
- `ReservationLedgerReader.strategy_available(...)` / `symbol_available(...)` / `total_free`

任一實作（StrategyRegistry、ReservationLedger）結構性即符合。

### D-2：CapitalReservationRule 把 reservation_id 寫 metadata

由 engine 在組 Decision 時讀取最後一條 reason 的 metadata.reservation_id 並寫入 Decision.reservation_id。

**替代方案**：rule 直接持有 Decision builder。

**理由**：保持 rule 純函式（無副作用 except its own state），Decision 組裝權留給 engine。

### D-3：ThrottleScaler 預設 no-op

ThrottleScaler 的設計用意是「未來動態 scaler 擴展」；本 change 預設 no-op（永遠 PASS），避免與 SystemStateRule 重複縮量。配置 `scaler` < 1.0 時主動參與；預設 scaler=1.0 無動作。

### D-4：StrategyBudgetCap 與 SymbolConcentrationCap 用 notional 推算 max_qty

實作公式：

```
notional_avail = ledger.strategy_available(sid) 或 ledger.symbol_available(sym)
max_qty = notional_avail / current_price
clamped_qty = min(current_size, max_qty)
```

intent.price 為 None（市價單）時用 ctx.market_data.get_last_price 作 reference。

## Risks

| Risk | Mitigation |
|------|-----------|
| **R-1** Protocol 結構性符合度誤判 | runtime_checkable + 測試 isinstance 確認 |
| **R-2** CapitalReservationRule 失敗時 reservation 已扣 | reserver.reserve 失敗即不寫 metadata，engine 看 verdict=REJECT 即不發 OrderSubmitted；reservation 邏輯本身未生成 reservation_id |
| **R-3** PriceSanityCheck 拒掉合理大幅波動單 | max_deviation_pct 由 config 調；極端市場可暫時放寬 |
| **R-4** 現價 0 或 None | 市價單以 last_price 替代；last_price <= 0 → CLAMP 為 0 並紀錄 warning |
