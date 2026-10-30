"""Wires the agents together and drives them bar by bar."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .agents import (
    ExecutionAgent,
    LLMStrategistAgent,
    MarketDataAgent,
    PortfolioManagerAgent,
    RiskManagerAgent,
    TechnicalAnalystAgent,
)
from .bus import MessageBus


@dataclass
class Config:
    symbol: str = "SYNTH"
    cash: float = 10_000.0
    fee_bps: float = 5.0
    slippage_bps: float = 5.0
    risk_per_trade: float = 0.02
    max_position: float = 0.95
    atr_mult: float = 2.5
    max_drawdown: float = 0.20
    allow_short: bool = False
    use_llm: bool = False
    llm_model: str = "claude-opus-5-5"
    llm_every: int = 5
    weights: dict = field(default_factory=lambda: {"technical": 0.7, "strategist": 0.3})


class TradingTeam:
    def __init__(self, data: pd.DataFrame, config: Config | None = None):
        self.config = cfg = config or Config()
        self.bus = MessageBus()
        self.market = MarketDataAgent(self.bus, data, cfg.symbol)
        self.execution = ExecutionAgent(self.bus, cfg.cash, cfg.fee_bps, cfg.slippage_bps)
        self.analyst = TechnicalAnalystAgent(self.bus)
        self.strategist = LLMStrategistAgent(self.bus, cfg.llm_model, cfg.llm_every) if cfg.use_llm else None
        self.risk = RiskManagerAgent(self.bus, cfg.risk_per_trade, cfg.max_position, cfg.atr_mult, cfg.max_drawdown)
        self.pm = PortfolioManagerAgent(self.bus, cfg.weights, allow_short=cfg.allow_short)

    @property
    def agents(self):
        return [a for a in (self.market, self.analyst, self.strategist, self.pm, self.risk, self.execution) if a]

    def run(self) -> dict:
        for i in range(len(self.market)):
            self.market.publish_bar(i)
            self.bus.publish_from("orchestrator", "cycle.decide", i)
        return self.report()

    def report(self) -> dict:
        curve = pd.Series(dict(self.execution.equity_curve))
        data = self.market.data
        rets = curve.pct_change().dropna()
        years = max(len(curve) / 252, 1e-9)
        total = curve.iloc[-1] / curve.iloc[0] - 1
        bh = data["close"].iloc[-1] / data["open"].iloc[0] - 1
        sharpe = float(np.sqrt(252) * rets.mean() / rets.std()) if rets.std() > 0 else 0.0
        max_dd = float((1 - curve / curve.cummax()).max())
        exits = [t for t in self.execution.trades if t["side"] == "SELL"]
        return {
            "final_equity": round(float(curve.iloc[-1]), 2),
            "total_return": round(float(total), 4),
            "cagr": round(float((1 + total) ** (1 / years) - 1), 4),
            "buy_and_hold_return": round(float(bh), 4),
            "sharpe": round(sharpe, 2),
            "max_drawdown": round(max_dd, 4),
            "trades": len(self.execution.trades),
            "stop_outs": sum(t["reason"] == "stop loss" for t in exits),
            "halted": self.risk.halted,
        }
