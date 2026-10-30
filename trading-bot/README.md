# Multi-Agent Trading Bot (paper trading)

A trading bot built as a **team of agents**. Each agent has one job, and they only talk to each other through a message bus.

```
            market.bar                  signal.*              order.proposal          order.approved
 MarketData ─────────► TechnicalAnalyst ────────► PortfolioMgr ─────────────► RiskManager ─────────────► Execution
     │                 Strategist (Claude) ──┘          ▲                         ▲   │ risk.halt          │
     │                                                  └── position.stopped ─────┼───┴────────────────────┤
     └──────────────────────────────── market.bar (fills at next open, trailing stops) ───────────────────┘
                                                                portfolio.update (equity → drawdown check) ┘
```

| Agent | Job |
|---|---|
| `market_data` | Owns the price feed (synthetic or Yahoo Finance) and sends out each bar |
| `technical_analyst` | Turns SMA trend, RSI and MACD into a score from -1 to +1 |
| `strategist` *(optional)* | Asks Claude for a second opinion on the analyst's report, with a confidence level |
| `portfolio_manager` | Combines the signals using confidence weights and proposes a target exposure. Uses hysteresis so it doesn't flip-flop |
| `risk_manager` | Sizes each trade so that hitting the stop costs about 2% of equity. Caps position size, sets an ATR stop, and **halts all trading** at a 20% drawdown |
| `execution` | Paper broker. Fills at the **next bar's open** (no look-ahead), charges fees and slippage, and trails stops |

## Run it

```bash
pip install -r requirements.txt

python main.py                         # offline backtest on synthetic prices
python main.py --symbol SPY            # backtest on real daily data
python main.py --symbol BTC-USD --short
python main.py --symbol SPY --signal   # just today's decision from the team
python main.py --verbose               # show every message between agents

export ANTHROPIC_API_KEY=...           # add the Claude strategist
python main.py --symbol SPY --llm --llm-every 5
```

The strategist uses `claude-opus-5-5` (change it with `Config.llm_model`) and returns structured JSON. It turns on server-side refusal fallback. In backtests it only calls Claude every `--llm-every` bars to keep costs down. If a call fails, the rest of the team keeps trading without it.

## Add your own agent

1. Subclass `bot.agents.Agent` and subscribe to the topics it needs (`market.bar`, `signal.technical`, …).
2. Publish your output with `self.send("signal.<name>", score=..., confidence=...)`.
3. Register it in `TradingTeam.__init__`, subscribe the portfolio manager to your topic, and give it a weight in `Config.weights`.

Some ideas: a news/sentiment agent, an on-chain or volume agent, a regime detector that turns down risk in choppy markets, or a live broker execution agent (for example Alpaca paper trading).

## Tests

```bash
python -m pytest -q tests
```

## ⚠️ Disclaimer

This is educational software and it trades **paper money only**. Backtests are not live results, and the sample strategy is not tuned or proven. Paper-trade any change for a long time before you think about real money. Never risk money you can't afford to lose.
