"""Run the multi-agent trading team.

    python main.py                      # offline backtest on synthetic prices
    python main.py --symbol SPY         # backtest on real data (needs yfinance)
    python main.py --symbol SPY --llm   # add the Claude strategist (needs ANTHROPIC_API_KEY)
    python main.py --signal --symbol SPY  # just print today's team decision
"""
from __future__ import annotations

import argparse
import json

from bot.agents.market_data import download_prices, synthetic_prices
from bot.agents.strategist import LLMStrategistAgent
from bot.orchestrator import Config, TradingTeam

QUIET = {"market.bar", "portfolio.update", "cycle.decide", "signal.technical", "signal.strategist"}


def main() -> None:
    p = argparse.ArgumentParser(description="Multi-agent paper-trading bot")
    p.add_argument("--symbol", help="Ticker to download with yfinance; omit for synthetic data")
    p.add_argument("--period", default="3y")
    p.add_argument("--cash", type=float, default=10_000)
    p.add_argument("--short", action="store_true", help="allow short positions")
    p.add_argument("--llm", action="store_true", help="enable the Claude strategist agent")
    p.add_argument("--llm-every", type=int, default=5, help="call Claude every N bars")
    p.add_argument("--signal", action="store_true", help="only show the decision for the latest bar")
    p.add_argument("--verbose", action="store_true", help="print every agent message")
    args = p.parse_args()

    data = download_prices(args.symbol, args.period) if args.symbol else synthetic_prices()
    if args.llm and not LLMStrategistAgent.available():
        print("! --llm needs ANTHROPIC_API_KEY; running without the strategist")
        args.llm = False

    cfg = Config(symbol=args.symbol or "SYNTH", cash=args.cash, allow_short=args.short,
                 use_llm=args.llm, llm_every=args.llm_every)

    if args.signal:
        # Replay quietly so indicators/state warm up, calling Claude only on the last bar.
        cfg.llm_every = 10**9
        team = TradingTeam(data, cfg)
        team.bus.keep_log = False
        for i in range(len(data) - 1):
            team.market.publish_bar(i)
            team.bus.publish_from("orchestrator", "cycle.decide", i)
        team.bus.keep_log = True
        if team.strategist:
            team.strategist._last_call_step = None
        team.market.publish_bar(len(data) - 1)
        team.bus.publish_from("orchestrator", "cycle.decide", len(data) - 1)
        for m in team.bus.log:
            if m.topic.startswith(("signal.", "order.", "risk.", "agent.")):
                print(f"[{m.sender:>17}] {m.topic:<18} {json.dumps(m.payload, default=str)}")
        print(f"\nCurrent target exposure: {team.pm.target:+.0%} of max size")
        return

    team = TradingTeam(data, cfg)
    print("Team:")
    for a in team.agents:
        print(f"  - {a.name:<17} {a.role}")
    result = team.run()

    for m in team.bus.log:
        if args.verbose or m.topic not in QUIET:
            when = m.payload.get("time", team.market.data.index[m.step])
            print(f"{str(when)[:10]} [{m.sender:>17}] {m.topic:<16} "
                  f"{json.dumps({k: v for k, v in m.payload.items() if k not in ('history', 'time')}, default=str)}")
    print("\nResults:")
    for k, v in result.items():
        print(f"  {k:<20} {v}")


if __name__ == "__main__":
    main()
