from __future__ import annotations

import json
import os

from .base import Agent

SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "description": "-1 strongly bearish .. +1 strongly bullish"},
        "confidence": {"type": "number", "description": "0..1"},
        "rationale": {"type": "string"},
    },
    "required": ["score", "confidence", "rationale"],
    "additionalProperties": False,
}

SYSTEM = (
    "You are the strategist on a small trading team. The technical analyst sends you indicator "
    "readings and recent closes for one symbol. Give a short-horizon (days to weeks) directional view. "
    "Be skeptical: return a score near 0 with low confidence when the picture is mixed."
)


class LLMStrategistAgent(Agent):
    """Job: second opinion. Asks Claude to reason over the analyst's report.

    Disabled unless ANTHROPIC_API_KEY (or another Anthropic credential) is available.
    Calls Claude at most once every `every` bars and reuses the last view in between.
    """

    name = "strategist"
    role = "Claude-powered discretionary view"

    def __init__(self, bus, model: str = "claude-opus-5-5", every: int = 1):
        super().__init__(bus)
        self.model = model
        self.every = max(1, every)
        self.last_view: dict | None = None
        self._last_call_step: int | None = None
        self._client = None
        self._closes: list[float] = []
        bus.subscribe("market.bar", lambda m: self._closes.append(float(m.payload["bar"]["close"])))
        bus.subscribe("signal.technical", self.on_technical)

    @property
    def client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def on_technical(self, msg) -> None:
        self.step = msg.step
        due = self._last_call_step is None or msg.step - self._last_call_step >= self.every
        if due:
            self._last_call_step = msg.step
            view = self.ask(msg.payload)
            if view is not None:
                self.last_view = view
        if self.last_view is not None:
            self.send("signal.strategist", **self.last_view)

    def ask(self, report: dict) -> dict | None:
        prompt = json.dumps(
            {
                "analyst_score": report["score"],
                "indicators": report["indicators"],
                "last_20_closes": [round(c, 2) for c in self._closes[-20:]],
            }
        )
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=2000,
                system=SYSTEM,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # network, auth, rate limit: the team carries on without us
            self.send("agent.error", error=f"{type(exc).__name__}: {exc}")
            return None
        if response.stop_reason == "refusal":
            return None
        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            return None
        view = json.loads(text)
        view["score"] = max(-1.0, min(1.0, float(view["score"])))
        view["confidence"] = max(0.0, min(1.0, float(view["confidence"])))
        return view

    @staticmethod
    def available() -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
