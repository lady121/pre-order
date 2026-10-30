from __future__ import annotations

from .base import Agent


class ExecutionAgent(Agent):
    """Job: place orders on a paper broker and manage stops.

    Orders approved on bar t fill at bar t+1's open (no look-ahead). Stops trail the
    best close since entry by the distance the risk manager chose.
    """

    name = "execution"
    role = "Paper broker: fills, fees, trailing stops"

    def __init__(self, bus, cash: float = 10_000.0, fee_bps: float = 5.0, slippage_bps: float = 5.0):
        super().__init__(bus)
        self.cash = cash
        self.shares = 0.0
        self.fee = fee_bps / 10_000
        self.slip = slippage_bps / 10_000
        self.pending: dict | None = None
        self.stop: float | None = None
        self.stop_pct: float | None = None
        self.best: float | None = None
        self.trades: list[dict] = []
        self.equity_curve: list[tuple] = []
        bus.subscribe("order.approved", self.on_approved)
        bus.subscribe("market.bar", self.on_bar)

    def equity(self, price: float) -> float:
        return self.cash + self.shares * price

    def on_approved(self, msg) -> None:
        self.pending = msg.payload

    def _trade_to(self, weight: float, price: float, time, reason: str) -> None:
        equity = self.equity(price)
        target_shares = equity * weight / price
        delta = target_shares - self.shares
        if abs(delta * price) < 1.0:
            return
        fill = price * (1 + self.slip if delta > 0 else 1 - self.slip)
        cost = abs(delta) * fill * self.fee
        self.cash -= delta * fill + cost
        self.shares = target_shares
        trade = {"time": time, "side": "BUY" if delta > 0 else "SELL", "shares": round(delta, 4),
                 "price": round(fill, 4), "fee": round(cost, 4), "reason": reason}
        self.trades.append(trade)
        self.send("order.filled", **trade)

    def on_bar(self, msg) -> None:
        self.step = msg.step
        bar, time = msg.payload["bar"], msg.payload["time"]

        if self.pending is not None:
            order, self.pending = self.pending, None
            self._trade_to(order["target_weight"], bar["open"], time, order.get("reason", ""))
            self.stop, self.stop_pct = order.get("stop"), order.get("stop_pct")
            self.best = bar["open"] if self.shares else None

        if self.shares and self.stop is not None:
            long = self.shares > 0
            hit = bar["low"] <= self.stop if long else bar["high"] >= self.stop
            if hit:
                exit_px = min(bar["open"], self.stop) if long else max(bar["open"], self.stop)
                self._trade_to(0.0, exit_px, time, "stop loss")
                self.stop = self.stop_pct = self.best = None
                self.send("position.stopped", price=round(exit_px, 4))
            elif self.stop_pct:
                self.best = max(self.best, bar["close"]) if long else min(self.best, bar["close"])
                trail = self.best * (1 - self.stop_pct) if long else self.best * (1 + self.stop_pct)
                self.stop = max(self.stop, trail) if long else min(self.stop, trail)

        eq = self.equity(bar["close"])
        self.equity_curve.append((time, eq))
        self.send("portfolio.update", equity=round(eq, 2), cash=round(self.cash, 2),
                  shares=round(self.shares, 4), price=round(bar["close"], 4))
