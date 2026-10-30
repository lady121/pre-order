from __future__ import annotations

from .base import Agent


class RiskManagerAgent(Agent):
    """Job: say no. Sizes positions, sets stop losses, and halts trading on big drawdowns."""

    name = "risk_manager"
    role = "Position sizing, stops, drawdown kill-switch"

    def __init__(self, bus, risk_per_trade: float = 0.02, max_position: float = 0.95,
                 atr_mult: float = 2.5, max_drawdown: float = 0.20):
        super().__init__(bus)
        self.risk_per_trade = risk_per_trade
        self.max_position = max_position
        self.atr_mult = atr_mult
        self.max_drawdown = max_drawdown
        self.atr = None
        self.price = None
        self.equity = None
        self.peak = None
        self.halted = False
        bus.subscribe("signal.technical", self.on_technical)
        bus.subscribe("portfolio.update", self.on_portfolio)
        bus.subscribe("order.proposal", self.on_proposal)

    def on_technical(self, msg) -> None:
        self.atr = msg.payload["indicators"]["atr"]
        self.price = msg.payload["indicators"]["close"]

    def on_portfolio(self, msg) -> None:
        self.equity = msg.payload["equity"]
        self.peak = max(self.peak or self.equity, self.equity)
        dd = 1 - self.equity / self.peak
        if not self.halted and dd >= self.max_drawdown:
            self.halted = True
            self.step = msg.step
            self.send("risk.halt", drawdown=round(dd, 4))
            self.send("order.approved", target_weight=0.0, stop=None, reason="drawdown halt")

    def on_proposal(self, msg) -> None:
        self.step = msg.step
        target = msg.payload["target_exposure"]
        if self.halted:
            self.send("order.rejected", reason="trading halted by drawdown limit", proposal=msg.payload)
            return
        if target == 0.0 or not self.atr or not self.price:
            self.send("order.approved", target_weight=0.0, stop=None, reason="flatten")
            return
        stop_dist = self.atr_mult * self.atr / self.price
        # Risk at most `risk_per_trade` of equity if the stop is hit.
        size_cap = min(self.max_position, self.risk_per_trade / stop_dist)
        weight = round(target * size_cap, 4)
        side = 1 if weight > 0 else -1
        stop = round(self.price * (1 - side * stop_dist), 4)
        self.send("order.approved", target_weight=weight, stop=stop, stop_pct=round(stop_dist, 4),
                  reason=f"stop {stop_dist:.1%} away, cap {size_cap:.0%}")
