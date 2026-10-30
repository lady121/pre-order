from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Agent


def synthetic_prices(n: int = 750, seed: int = 7, start: float = 100.0) -> pd.DataFrame:
    """Random-walk OHLCV with alternating bull/bear/chop regimes, for offline testing."""
    rng = np.random.default_rng(seed)
    drifts = rng.choice([0.0012, -0.0010, 0.0], size=n // 60 + 1)
    drift = np.repeat(drifts, 60)[:n]
    rets = drift + rng.normal(0, 0.015, n)
    close = start * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[start], close[:-1]]) * (1 + rng.normal(0, 0.002, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.006, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.006, n)))
    volume = rng.integers(1_000_000, 5_000_000, n)
    idx = pd.bdate_range("2023-01-02", periods=n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx)


def download_prices(symbol: str, period: str = "3y", interval: str = "1d") -> pd.DataFrame:
    import yfinance as yf  # optional dependency

    df = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data returned for {symbol}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    return df.dropna()


class MarketDataAgent(Agent):
    """Job: own the price feed and broadcast each new bar (plus history) to everyone."""

    name = "market_data"
    role = "Feeds price bars to the team"

    def __init__(self, bus, data: pd.DataFrame, symbol: str):
        super().__init__(bus)
        self.data = data
        self.symbol = symbol

    def __len__(self) -> int:
        return len(self.data)

    def publish_bar(self, i: int) -> None:
        self.step = i
        bar = self.data.iloc[i]
        self.send(
            "market.bar",
            symbol=self.symbol,
            time=self.data.index[i],
            bar=bar.to_dict(),
            history=self.data.iloc[: i + 1],
        )
