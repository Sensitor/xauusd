"""Synthetic XAUUSD data.

Used by tests and the runnable demo so the whole pipeline can execute with zero
external dependencies (no broker, no API keys). Higher timeframes are *resampled*
from a single M5 base series, exactly as a real feed would aggregate, so the
multi-timeframe agents see internally consistent structure.

This is for plumbing/validation only — never mistake synthetic backtest numbers
for evidence of edge.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from goldmind.core.context import MarketContext
from goldmind.core.enums import Timeframe
from goldmind.core.schemas import AccountState

_RESAMPLE_RULE = {Timeframe.M15: "15min", Timeframe.H1: "1h", Timeframe.H4: "4h"}
_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def generate_ohlcv(
    periods: int = 1500,
    *,
    start_price: float = 2350.0,
    drift: float = 0.0,
    volatility: float = 0.0009,
    seed: int | None = 7,
    end: datetime | None = None,
    freq_minutes: int = 5,
    mean_revert: bool = False,
    kappa: float = 0.04,
) -> pd.DataFrame:
    """Generate a base M5 OHLCV frame.

    Default is a Gaussian random walk with ``drift``. With ``mean_revert=True`` the
    log-price follows an Ornstein-Uhlenbeck process around ``start_price`` — a
    genuinely *ranging* market (low ADX), as opposed to a zero-drift random walk
    whose ADX can still wander above the trending threshold by chance.
    """
    rng = np.random.default_rng(seed)
    if mean_revert:
        log_mean = np.log(start_price)
        x = np.empty(periods)
        x[0] = log_mean
        shocks = rng.normal(0.0, volatility, periods)
        for t in range(1, periods):
            x[t] = x[t - 1] + kappa * (log_mean - x[t - 1]) + shocks[t]
        close = np.exp(x)
    else:
        rets = rng.normal(loc=drift, scale=volatility, size=periods)
        close = start_price * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[start_price], close[:-1]])
    # Intrabar wicks proportional to volatility.
    wick = np.abs(rng.normal(0, volatility, periods)) * close
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick
    volume = rng.integers(80, 400, periods).astype(float)

    end = end or datetime.now(UTC).replace(second=0, microsecond=0)
    idx = pd.date_range(end=end, periods=periods, freq=f"{freq_minutes}min", tz="UTC")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx)


def resample(base_m5: pd.DataFrame, tf: Timeframe) -> pd.DataFrame:
    if tf is Timeframe.M5:
        return base_m5
    return base_m5.resample(_RESAMPLE_RULE[tf], label="right", closed="right").agg(_AGG).dropna()


def build_synthetic_context(
    *,
    as_of: datetime | None = None,
    n_m5: int = 2600,  # ~216 H1 bars -> EMA200 on H1 is available
    drift: float = 0.0,
    volatility: float = 0.0009,
    seed: int | None = 7,
    equity: float = 100_000.0,
    timeframes: tuple[Timeframe, ...] = (Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4),
    account: AccountState | None = None,
    mean_revert: bool = False,
) -> MarketContext:
    base = generate_ohlcv(n_m5, drift=drift, volatility=volatility, seed=seed, end=as_of, mean_revert=mean_revert)
    candles = {tf: resample(base, tf) for tf in timeframes}
    as_of = as_of or base.index[-1].to_pydatetime()
    acct = account or AccountState(equity=equity, balance=equity, peak_equity=equity)
    return MarketContext(symbol="XAUUSD", as_of=as_of, candles=candles, account=acct)
