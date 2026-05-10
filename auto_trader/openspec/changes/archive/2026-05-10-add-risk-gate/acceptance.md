# add-risk-gate — 驗收紀錄

> 對應 task 16.1–16.5。本文件為 change archive 前的最終驗證快照。

## 16.1 OpenSpec 結構驗證

```
$ openspec validate add-risk-gate
Change 'add-risk-gate' is valid
```

artifacts 完整：`proposal.md` / `design.md` / `specs/risk-gate/spec.md` / `tasks.md`。

## 16.2 Spec scenario 對測試覆蓋對照

`spec.md` 共 14 條 SHALL requirement / 41 個 Given-When-Then scenario。
所有 scenario 至少有一個 test case 覆蓋（直接或間接）。

| Requirement | scenario | 覆蓋測試檔 |
|-------------|---------|-----------|
| 系統狀態機維護全系統風險狀態 | 服務首次啟動使用預設狀態 | `test_state_machine.py::test_first_startup_defaults_to_normal` |
| 系統狀態機維護全系統風險狀態 | 服務重啟讀回先前狀態 | `test_state_machine.py::test_restart_loads_previous_state_throttled`, `test_integration.py::test_state_persistence_across_restart` |
| 系統狀態機維護全系統風險狀態 | 不可越級回升 | `test_state_machine.py::test_transition_halted_does_not_auto_recover` |
| 系統狀態轉換依凍結閾值自動觸發 | -2% 進入 WARNING | `test_state_machine.py::test_transition_normal_to_warning_at_minus_2_pct`, `test_tick_normal_to_warning_publishes_event` |
| 系統狀態轉換依凍結閾值自動觸發 | -5% 跨級進入 HALTED | `test_state_machine.py::test_transition_warning_to_halted_skipping_throttled` |
| 系統狀態轉換依凍結閾值自動觸發 | WARNING 條件解除回 NORMAL | `test_state_machine.py::test_transition_warning_back_to_normal_when_pnl_recovers` |
| 系統狀態轉換依凍結閾值自動觸發 | HALTED 不自動回升 | `test_state_machine.py::test_transition_halted_does_not_auto_recover` |
| HALTED 與 KILL_SWITCH 必須人工解鎖 | HALTED 接受人工 reset | `test_state_machine.py::test_manual_reset_from_halted_succeeds` |
| HALTED 與 KILL_SWITCH 必須人工解鎖 | KILL_SWITCH 觸發自動全平 | `test_state_machine.py::test_kill_switch_triggers_emergency_flatten_event`, `test_kill_switch_publishes_state_changed_then_flatten` |
| HALTED 與 KILL_SWITCH 必須人工解鎖 | 冷靜期內拒 reset | `test_state_machine.py::test_kill_switch_reset_within_cooling_rejected` |
| HALTED 與 KILL_SWITCH 必須人工解鎖 | 冷靜期後接受 reset | `test_state_machine.py::test_kill_switch_reset_after_cooling_succeeds` |
| MAINTENANCE 為人工專用且阻擋所有交易 | 人工進入維護模式 | `test_state_machine.py::test_enter_maintenance_from_any_state` |
| MAINTENANCE 為人工專用且阻擋所有交易 | 維護期間拒絕 OrderIntent | `test_rule_system_state.py::test_maintenance_state_rejects` |
| 規則引擎採短路評估 | reject 短路 | `test_engine.py::test_reject_rule_short_circuits_subsequent` |
| 規則引擎採短路評估 | clamp 累積收斂 | `test_engine.py::test_clamp_rules_accumulate_size_reduction` |
| 規則引擎採短路評估 | 違反單調遞減為 bug | `test_engine.py::test_bad_clamp_in_debug_raises`, `test_bad_clamp_in_production_ignored` |
| Decision 與 RuleVerdict 為不可變值物件 | Decision 序列化 | `test_decision.py::test_decision_to_dict_json_serializable` |
| Decision 與 RuleVerdict 為不可變值物件 | Decision 不可變 | `test_decision.py::test_decision_immutable` |
| SystemStateRule 依 FSM 狀態決定門檻 | NORMAL 通過 / THROTTLED 縮量 / HALTED 拒 | `test_rule_system_state.py::test_normal_state_passes`, `test_throttled_state_clamps_50_pct`, `test_halted_state_rejects` |
| IdempotencyRule 以 signal_id 5 分鐘 TTL 去重 | 首次通過 | `test_rule_idempotency.py::test_first_occurrence_passes` |
| IdempotencyRule 以 signal_id 5 分鐘 TTL 去重 | TTL 內重送拒 | `test_rule_idempotency.py::test_duplicate_within_ttl_rejected` |
| IdempotencyRule 以 signal_id 5 分鐘 TTL 去重 | TTL 後重送通過 | `test_rule_idempotency.py::test_duplicate_after_ttl_passes` |
| IdempotencyRule 以 signal_id 5 分鐘 TTL 去重 | LRU 淘汰 | `test_rule_idempotency.py::test_lru_eviction_on_max_entries` |
| 未實作規則須提供契約 stub | NotImplementedError | `test_rule_stubs.py::test_stub_raises_not_implemented` (parametrized × 9) |
| 未實作規則須提供契約 stub | docstring 凍結 | `test_rule_stubs.py::test_stub_has_docstring` (parametrized × 9) |
| CapitalReserver 為單一 actor 序列化處理預留 | 三道全通過 | `test_capital_reserver.py::test_reserve_success_updates_ledger_and_emits_event` |
| CapitalReserver 為單一 actor 序列化處理預留 | 任一不足拒絕 | `test_capital_reserver.py::test_reserve_strategy_insufficient_returns_failure`, `test_reserve_symbol_insufficient_returns_failure` |
| CapitalReserver 為單一 actor 序列化處理預留 | FCFS 順序 | `test_capital_reserver.py::test_fcfs_concurrent_reservations_consistent_ledger`, `test_fcfs_first_come_first_served_order` |
| CapitalReserver 為單一 actor 序列化處理預留 | 釋放歸還 + 事件 | `test_capital_reserver.py::test_release_returns_capacity_and_emits_event` |
| CapitalReserver 為單一 actor 序列化處理預留 | release 冪等 | `test_capital_reserver.py::test_release_idempotent_on_duplicate_call`, `test_release_unknown_id_is_noop` |
| 風控閘僅依賴 ports 介面與下游互動 | 注入測試替身 | `test_ports.py::*` (8 fakes 結構驗證) |
| 風控閘僅依賴 ports 介面與下游互動 | 違反 ISP 被攔截 | `mypy --strict` gate（CI 把關） |
| 配置以 YAML 表達且啟動時驗證 | 啟動時驗證成功 | `test_config.py::test_default_config_yaml_loads_successfully` |
| 配置以 YAML 表達且啟動時驗證 | 缺欄位阻止啟動 | `test_config.py::test_missing_fsm_thresholds_field_raises` |
| 配置以 YAML 表達且啟動時驗證 | 型別錯誤阻止啟動 | `test_config.py::test_wrong_type_daily_pnl_kill_raises` |
| 所有時間相依邏輯透過 Clock Protocol 注入 | 注入測試 Clock 控制時間流 | `test_frozen_clock.py::*` 全部 13 tests |
| 所有時間相依邏輯透過 Clock Protocol 注入 | 跨日重置依配置時區 | `test_daily_pnl.py::test_reset_on_utc_midnight_boundary`, `test_reset_with_taipei_timezone` |
| 所有風控決策與狀態變更須發布事件供審計 | 每筆 Decision 觸發事件 | `test_engine.py::test_decision_emitted_event_per_evaluation` |
| 所有風控決策與狀態變更須發布事件供審計 | KILL_SWITCH 觸發兩個事件 | `test_state_machine.py::test_kill_switch_publishes_state_changed_then_flatten` |
| 所有風控決策與狀態變更須發布事件供審計 | 事件可序列化 | `test_events.py::test_event_serialization_roundtrip_via_publisher` |
| 啟動時暖機 30 秒不接受 OrderIntent | 暖機期內拒 | `test_gate.py::test_warming_up_rejects_order_intent`, `test_integration.py::test_warming_up_lifecycle_then_normal` |
| 啟動時暖機 30 秒不接受 OrderIntent | 暖機後正常處理 | `test_gate.py::test_after_warming_up_routes_to_engine` |

## 16.3 Mypy 嚴格模式

```
$ mypy risk/ tests/
Success: no issues found in 46 source files
```

`pyproject.toml` 設定 `strict = true`，包含：

- `disallow_untyped_defs`、`disallow_any_generics`、`no_implicit_optional`
- `warn_return_any`、`warn_redundant_casts`、`warn_unused_ignores`
- `warn_unreachable`、`disallow_incomplete_defs`、`check_untyped_defs`

## 16.4 測試覆蓋率

```
$ pytest --cov=risk -q
TOTAL  832 lines  18 missed  98%
235 passed
```

| 模組 | 覆蓋率 |
|------|-------|
| `risk/decision.py` | 100% |
| `risk/events.py` | 100% |
| `risk/ports.py` | 100% |
| `risk/types.py` | 100% |
| `risk/rules/base.py` | 100% |
| `risk/rules/_stubs.py` | 100% |
| `risk/rules/idempotency.py` | 100% |
| `risk/rules/system_state.py` | 100% |
| `risk/state/states.py` | 100% |
| `risk/state/transitions.py` | 100% |
| `risk/state/persistence.py` | 100% |
| `risk/state/daily_pnl.py` | 100% |
| `risk/config.py` | 98% |
| `risk/state/machine.py` | 98% |
| `risk/reservation/ledger.py` | 98% |
| `risk/reservation/reserver.py` | 97% |
| `risk/gate.py` | 96% |
| `risk/engine.py` | 91% |
| `risk/adapters/system_clock.py` | 75% |

整體 **98%** > 90% 目標。

## 16.5 部署 Checklist 與已知限制

### MVP 限制（後續 change 處理）

| 項目 | 限制 | 後續 change |
|------|------|------------|
| FSM 狀態持久化 | `InMemoryStateStore` 僅記憶體 | `add-sqlite-state-store` |
| 訊號去重快取 | 重啟丟失 | 同上 |
| ledger 預算與持倉 | 重啟回到初始 | 同上 + reconciliation 整合 |
| 規則 hot reload | 不支援，重啟才換 | 視需求 |
| 9 條規則具體邏輯 | stub 拋 NotImplementedError | 各別 change（依 risk/rules/README.md 對照表） |
| Telegram / Email 告警 | 未提供 | `add-observability` |
| metrics_provider | 由呼叫端注入 | `add-strategy-host`、`add-reconciliation` |
| KILL_SWITCH 全平實作 | 僅發 EmergencyFlattenRequested 事件 | `add-order-execution` |

### 部署前驗證 checklist

- [ ] `openspec validate add-risk-gate` 通過
- [ ] `mypy --strict risk/ tests/` 通過
- [ ] `pytest -x` 通過
- [ ] `ruff check risk/ tests/` 通過
- [ ] `pytest --cov=risk` ≥ 90%
- [ ] 啟動日誌包含 `params_hash`，與預期配置版本一致
- [ ] `config/risk.yaml` 之觸發閾值與資金限額符合本次部署的風險容忍度
- [ ] StateStore 已確認為 InMemoryStateStore，重啟會喪失狀態（prod 應改用 SqliteStateStore，後續 change）
- [ ] 與外部 capability 整合前先以 `RiskGate` 單元測試驗證（參考 `tests/test_gate.py`）

### 後續 change 預告

下一個建議的 change：

1. **`add-signal-ingestion`**：實作 4 條 SignalSource adapter（TradingView Webhook / MT5 / Vibe Shadow Scanner / Manual CLI），對應 `docs/design-brief.md` 第 5 節
2. **`add-strategy-host`**：實作 LogicalBook + Strategy lifecycle + StrategyRegistry，提供 metrics_provider 給 RiskGate
3. **`add-sqlite-event-log`**：將 EventPublisher 廣播持久化至 SQLite，啟用審計與回放
