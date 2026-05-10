# vibe-auto-trader

個人化自動交易機器人，以 [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) 為策略研發與訊號來源，自建端到端執行層（訊號接收 + 風險控制 + 訂單執行 + 對帳 + 監控）。

> Status：MVP 開發中。當前已完成 `risk-gate` capability（風控閘）。

## 架構（六大 capability）

```
TradingView Alert / Vibe-Trading scan
        ▼
┌─────────────────────────────────┐
│ 1. signal-ingestion             │  訊號入口 + 路由 + 去重
└────────┬────────────────────────┘
         ▼ Signal
┌─────────────────────────────────┐
│ 2. strategy-host                │  策略生命週期 + LogicalBook
└────────┬────────────────────────┘
         ▼ OrderIntent
┌─────────────────────────────────┐
│ 3. risk-gate         ★ 已完成   │  FSM + RuleEngine + CapitalReserver
└────────┬────────────────────────┘
         ▼ Decision
┌─────────────────────────────────┐
│ 4. order-execution              │  CCXT → Exchange
└────────┬────────────────────────┘
         ▼ Fill events
┌─────────────────────────────────┐
│ 5. reconciliation               │  歸因 + LogicalBook 更新
└────────┬────────────────────────┘
         ▼
┌─────────────────────────────────┐
│ 6. observability                │  Audit log + Telegram + Kill switch
└─────────────────────────────────┘
```

## Quickstart

### 1. 安裝

```bash
git clone git@github.com:chaokenyuan/vibe-auto-trader.git
cd vibe-auto-trader
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. 驗證（mypy + pytest + ruff）

```bash
mypy risk/ signals/ strategies/ execution/ reconciliation/ observability/ reservation_bridge/ tests/
pytest -q
ruff check risk/ signals/ strategies/ execution/ reconciliation/ observability/ reservation_bridge/ tests/
pytest --cov=risk --cov=signals --cov=strategies --cov=execution --cov=reconciliation --cov=observability --cov=reservation_bridge
```

### 3. 跑端到端 demo（不需真交易所/TV 帳號）

```bash
python scripts/demo.py
```

`scripts/demo.py` 用 ASGITransport + Mock adapter 串起全 8 個 capability，
13 個 step 印出訊號從 webhook 進來、過 RiskGate、下單、fill 回報、reservation 釋放
與 KILL_SWITCH 告警的完整流程。

### 4. 在 Python 中使用 RiskGate（單獨用）

```python
from decimal import Decimal
from risk.gate import RiskGate

gate = RiskGate.from_config(
    config_path="config/risk.yaml",
    total_equity=Decimal("10000"),
    strategy_budgets={"vibe_btc_v1": Decimal("5000")},
    symbol_caps={"BTCUSDT": Decimal("4000")},
    positions=...,       # 由 reconciliation capability 提供
    market_data=...,     # 由 strategy-host 提供
    config_reader=...,
)

await gate.start()
decision = await gate.evaluate(intent)
await gate.shutdown()
```

詳細使用說明見 [risk/README.md](risk/README.md)。

## 文件導覽

| 文件 | 用途 |
|------|------|
| [docs/design-brief.md](docs/design-brief.md) | 探索階段成果（A/C/D 階段共識基線、附錄 C 為 Vibe-Trading 補課修訂） |
| [risk/README.md](risk/README.md) | risk-gate capability 完整使用說明 + 雙層架構圖 |
| [risk/rules/README.md](risk/rules/README.md) | 11 條規則對照表（已實作/stub） |
| [config/README.md](config/README.md) | YAML 配置欄位速查 |
| [openspec/specs/risk-gate/spec.md](openspec/specs/risk-gate/spec.md) | 風控閘 14 條 SHALL requirement + 41 個 scenario |
| [openspec/changes/add-risk-gate/](openspec/changes/add-risk-gate/) | 第一個 OpenSpec change（proposal/design/specs/tasks） |

## 開發狀態

| Capability | 狀態 | OpenSpec change |
|-----------|------|-----------------|
| risk-gate | 完成 archived | `add-risk-gate` |
| signal-ingestion | 完成 archived | `add-signal-ingestion` |
| strategy-host | 完成 archived | `add-strategy-host` |
| order-execution | 完成 archived | `add-order-execution` |
| reconciliation | 完成 archived | `add-reconciliation` |
| observability | 完成 archived | `add-observability` |

**全六個 capability 完整實作**：109 source files、385 tests passed、mypy strict / ruff clean。

## 開發流程

本專案採用 [OpenSpec](https://github.com/Fission-AI/OpenSpec) 規格驅動開發：

```
explore → propose → design → specs → tasks → apply → verify → archive
```

每個新功能先寫 spec 取得共識，才進實作；spec 與代碼共同 commit。

## 法務與風險

- License: MIT
- 個人自用研究專案，**不對外提供金融服務**
- 自動交易涉及實質金錢損失風險，請在 testnet 充分驗證後才考慮實盤
- 詳見 [docs/design-brief.md 附錄 C](docs/design-brief.md)
