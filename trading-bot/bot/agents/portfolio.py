from __future__ import annotations

from .base import Agent


class PortfolioManagerAgent(Agent):
    """Job: listen to every analyst, weigh their votes, and propose a target exposure."""

    name = "portfolio_manager"
    role = "Combines signals into a trade proposal"

    def __init__(self, bus, weights: dict[str, float] | None = None, entry: float = 0.2,
                 exit: float = 0.0, allow_short: bool = False):
        super().__init__(bus)
        self.weights = weights or {"technical": 0.7, "strategist": 0.3}
        self.entry, self.exit, self.allow_short = entry, exit, allow_short
        self.signals: dict[str, dict] = {}
        self.target = 0.0
        bus.subscribe("signal.technical", lambda m: self.signals.__setitem__("technical", m.payload))
        bus.subscribe("signal.strategist", lambda m: self.signals.__setitem__("strategist", m.payload))
        bus.subscribe("cycle.decide", self.decide)
        bus.subscribe("position.stopped", lambda m: setattr(self, "target", 0.0))
        bus.subscribe("risk.halt", lambda m: setattr(self, "target", 0.0))

    def combined_score(self) -> float | None:
        total, wsum = 0.0, 0.0
        for source, sig in self.signals.items():
            w = self.weights.get(source, 0.0) * sig.get("confidence", 1.0)
            total += w * sig["score"]
            wsum += w
        return total / wsum if wsum else None

    def decide(self, msg) -> None:
        self.step = msg.step
        score = self.combined_score()
        self.signals.clear()
        if score is None:
            return
        # Hysteresis: need `entry` conviction to open, drop below `exit` to close.
        if score >= self.entry:
            target = min(1.0, score / 0.6)
        elif score <= -self.entry and self.allow_short:
            target = max(-1.0, score / 0.6)
        elif self.target > 0 and score > self.exit:
            target = self.target
        elif self.target < 0 and score < -self.exit:
            target = self.target
        else:
            target = 0.0
        if target == self.target or (abs(target - self.target) < 0.25 and target != 0.0):
            return  # ignore small rebalances to save fees
        self.target = target
        self.send("order.proposal", target_exposure=round(target, 3), score=round(score, 4))
