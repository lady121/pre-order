from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Agent


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift()
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


class TechnicalAnalystAgent(Agent):
    """Job: read the chart. Scores trend, momentum and MACD into one number in [-1, 1]."""

    name = "technical_analyst"
    role = "Chart indicators: SMA trend, RSI, MACD"

    def __init__(self, bus, fast: int = 20, slow: int = 50):
        super().__init__(bus)
        self.fast, self.slow = fast, slow
        bus.subscribe("market.bar", self.on_bar)

    def on_bar(self, msg) -> None:
        self.step = msg.step
        df: pd.DataFrame = msg.payload["history"]
        if len(df) < self.slow + 1:
            return
        close = df["close"]
        sma_f = close.rolling(self.fast).mean().iloc[-1]
        sma_s = close.rolling(self.slow).mean().iloc[-1]
        r = rsi(close).iloc[-1]
        macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
        hist = (macd - macd.ewm(span=9, adjust=False).mean()).iloc[-1]
        a = atr(df).iloc[-1]

        trend = float(np.tanh((sma_f / sma_s - 1) * 25))
        # RSI: trend-following in the middle, fade extremes
        momentum = float(np.clip((r - 50) / 20, -1, 1))
        if r > 75:
            momentum = -0.5
        elif r < 25:
            momentum = 0.5
        macd_score = float(np.tanh(hist / (a + 1e-9) * 3))
        score = 0.5 * trend + 0.25 * momentum + 0.25 * macd_score

        self.send(
            "signal.technical",
            score=round(score, 4),
            indicators={
                "sma_fast": round(float(sma_f), 4),
                "sma_slow": round(float(sma_s), 4),
                "rsi": round(float(r), 2),
                "macd_hist": round(float(hist), 4),
                "atr": round(float(a), 4),
                "close": round(float(close.iloc[-1]), 4),
            },
        )
