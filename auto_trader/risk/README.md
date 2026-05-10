# risk-gate capability

風控閘是 vibe-auto-trader 系統的命脈，吸收所有「該不該下這筆單」的判斷邏輯。
所有訊號通過 strategy-host 後產出 `OrderIntent`，必須先過 `RiskGate.evaluate()` 才能交給 order-execution。

## 模組結構

```
risk/
├── gate.py           RiskGate 對外門面（capability 唯一進入點）
├── decision.py       Decision / RuleVerdict 不可變值物件 + Verdict / Outcome 列舉
├── types.py          OrderIntent / Position / ReservationResult / Side
├── events.py         Event 基底 + 7 個具體事件型別
├── config.py         pydantic v2 配置模型（FsmThresholds / RiskConfig 等）
├── engine.py         RuleEngine（Layer 2 編排器）
├── ports.py          DIP 邊界（Clock / Position / MarketData / Config / EventPublisher / StateStore Protocols）
├── _serialize.py     共用序列化工具
├── adapters/         Protocol 的具體實作
│   ├── system_clock.py        SystemClock（datetime.now(UTC)）
│   └── in_memory_publisher.py InMemoryEventPublisher（asyncio fan-out）
├── state/            Layer 1 系統狀態機
│   ├── states.py     SystemState 列舉（NORMAL / WARNING / THROTTLED / HALTED / KILL_SWITCH / MAINTENANCE）
│   ├── transitions.py 純函式 evaluate_transition
│   ├── persistence.py InMemoryStateStore
│   ├── machine.py    StateMachine + tick / start / stop / reset
│   └── daily_pnl.py  DailyPnlTracker（跨日重置）
├── rules/            Layer 2 規則集
│   ├── base.py       RuleContext + RiskRule / RejectRule / ClampRule Protocols
│   ├── system_state.py  SystemStateRule（已實作）
│   ├── idempotency.py   IdempotencyRule（已實作）
│   └── _stubs.py     另 9 條規則 stub
└── reservation/      原子資金預留 actor
    ├── ledger.py     ReservationLedger（三層追蹤）
    └── reserver.py   CapitalReserver（asyncio.Queue actor）
```

## 對外進入點

```python
from decimal import Decimal
from risk.gate import RiskGate

gate = RiskGate.from_config(
    config_path="config/risk.yaml",
    total_equity=Decimal("10000"),
    strategy_budgets={"vibe_btc_v1": Decimal("5000")},
    symbol_caps={"BTCUSDT": Decimal("4000")},
    positions=...,       # 由 reconciliation capability 提供
    market_data=...,     # 由 strategy-host 或 observability 提供
    config_reader=...,   # 配置動態讀取（MVP 為 in-memory）
)

await gate.start()       # 啟動 reserver、進入 30 秒暖機
decision = await gate.evaluate(intent)
await gate.shutdown()
```

## 雙層架構

### Layer 1：系統狀態機（FSM）

慢變數，每 60 秒 tick 一次，依日內 PnL 與 API 健康度自動轉換狀態。

| 狀態 | 收訊 | 下單 | 持倉 | 退出方式 |
|------|------|------|------|---------|
| NORMAL | 接 | 100% | 正常 | 自動升級 |
| WARNING | 接 | 100% | 正常 | 條件回正自動降級 |
| THROTTLED | 接 | 50% | 正常 | 條件滿足自動降級 |
| HALTED | 拒 | 0 | 持有 | **人工 reset** |
| KILL_SWITCH | 拒 | 0 | **全平** | **人工 + 4h 冷靜期** |
| MAINTENANCE | 拒 | 0 | 不動 | 人工 |

預設閾值（可由 `config/risk.yaml` 覆寫）：

- 日內 PnL < -2% → WARNING
- 日內 PnL < -3% 或 API error rate > 5% → THROTTLED
- 日內 PnL < -5% → HALTED
- 日內 PnL < -7% → KILL_SWITCH

### Layer 2：規則引擎（RuleEngine）

快變數，每筆 OrderIntent 即時評估。短路機制：

```
reject 類規則 → 任一 REJECT 即終止
clamp 類規則 → 累積套用，size 單調遞減
原子預留      → 最後一道，向 CapitalReserver 申請
```

11 條規則的執行順序由 `config/risk.yaml` 的 `rules.enabled` 清單控制。

## 擴充新規則的 SOP

1. 在 `risk/rules/` 新增檔案，定義類別實作 `RiskRule` Protocol：
   ```python
   from risk.rules.base import RuleContext
   from risk.decision import Outcome, RuleVerdict

   class MyRule:
       name = "MyRule"

       def evaluate(self, ctx: RuleContext) -> RuleVerdict:
           ...
   ```
2. 在 `config/risk.yaml` 的 `rules.enabled` 清單中加入 `"MyRule"`，並在 `rules.params` 加入規則參數
3. 在 `risk/gate.py` 的 `_build_rules` 中新增建構邏輯
4. 撰寫單元測試覆蓋 PASS / CLAMP / REJECT 三種 outcome

## 設計原則

- **SOLID**：所有元件透過 `ports.py` 的 Protocol 互動，無具體 Adapter 依賴
- **不可變性**：所有值物件（Decision、Event、OrderIntent 等）為 frozen dataclass
- **可審計**：每筆 Decision 帶完整 `reasons: list[RuleVerdict]`，事件透過 `EventPublisher` 廣播
- **時間抽象**：所有時間相依邏輯透過注入的 `Clock`，可被 FrozenClock 控制以利測試
- **單例寫者**：StateMachine、RuleEngine、CapitalReserver 全系統單例；多 strategy 共用

## 已知限制（MVP）

- 持久化僅 in-memory；服務重啟丟失訊號去重快取與 ledger（FSM 狀態可選擇性持久化）
- 9 條規則仍為 stub，未實作具體邏輯（`SignalFreshnessRule`、`PerOrderSizeCap` 等）
- 無 hot reload，配置變更需重啟
- CapitalReserver 為單一 actor 序列化，預估 100s req/s 量級內適用

## 相關文件

- 需求規格：`openspec/specs/risk-gate/spec.md`
- 設計理由：`openspec/changes/add-risk-gate/design.md`
- 變更紀錄：`openspec/changes/add-risk-gate/proposal.md`
- 探索成果：`docs/design-brief.md`
