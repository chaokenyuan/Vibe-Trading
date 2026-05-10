# strategy-host capability

策略主機：把 Signal 路由到對應 Strategy、產生 OrderIntent、過 RiskGate、送往 OrderSink。

## 模組結構

```
strategies/
├── types.py            StrategyState、LogicalPosition、Fill
├── ports.py            Strategy / OrderSink Protocol
├── book.py             LogicalBook（每策略持倉）
├── registry.py         StrategyRegistry（取代 signal-ingestion stub）
├── host.py             StrategyHost（SignalConsumer 編排器）
└── strategies/
    └── passthrough.py  PassthroughStrategy 示範
```

## 對外進入點

```python
from strategies.host import StrategyHost
from strategies.registry import StrategyRegistry
from strategies.strategies.passthrough import PassthroughStrategy
from strategies.types import StrategyState

registry = StrategyRegistry()
strategy = PassthroughStrategy(strategy_id="A", strategy_version="1.0", params_hash="h")
registry.register(strategy)
registry.set_state("A", StrategyState.ACTIVE)

host = StrategyHost(registry=registry, risk_gate=risk_gate, order_sink=order_sink)

# 把 host 傳給 SignalRouter（host 是 SignalConsumer）
signal_router.subscribe(host)
```

## 訊號到訂單的鏈路

```
SignalRouter → host.on_signal(signal)
              ↓ registry lookup + state check
              ↓ strategy.on_signal(signal) → list[OrderIntent]
              ↓ for each intent
              ↓ risk_gate.evaluate → Decision
              ↓ if APPROVE → order_sink.submit(intent, decision, client_order_id)
```

## client_order_id 編碼

```
{strategy_id}.{signal_id_short}.{seq}
例：vibe_btc_v1.abc123def456.1
```

供 reconciliation capability 解碼回 strategy_id。

## 設計筆記

- Strategy.on_signal 拋例外 → 該 strategy 進入 FAILED，後續訊號 skip
- E4 凍結：crash 不自動平倉，等人工
- LogicalBook 為 mutable 但 asyncio 單執行緒保證並發安全

## 與其他 capability 的整合

- 上游：signal-ingestion 透過 SignalConsumer Protocol 接 host
- 下游：order-execution 提供 OrderSink 實作（後續 change）
- 對帳：reconciliation 收 Fill 後呼叫 LogicalBook.apply_fill 與 CapitalReserver.release（後續 change）

## 相關文件

- 需求規格：`openspec/specs/strategy-host/spec.md`
- 設計理由：`openspec/changes/add-strategy-host/design.md`
