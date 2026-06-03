"""Synthetic XAUUSD data.

Used by tests and the runnable demo so the whole pipeline can execute with zero
external dependencies (no broker, no API keys). Higher timeframes are *resampled*
from a single M5 base series, exactly as a real feed would aggregate, so the
multi-timeframe agents see internally consistent structure.

This is for plumbing/validation only — never mistake synthetic backtest numbers
for evidence of edge.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


# A coherent "dovish surprise + risk-off" bullish-gold narrative. The price drift,
# macro digest, and headlines all point the same way so the demo tells one story
# and the agents corroborate rather than contradict.
_DEMO_DIGEST = (
    "US CPI surprised cooler (3.1% vs 3.4% expected) and core PPI softened; the "
    "labor market is loosening (unemployment ticked to 4.1%). Fed funds futures now "
    "price an earlier cut and several FOMC members struck a dovish tone. DXY rolled "
    "over from its highs and the US 10Y yield eased ~12bp on the week. Geopolitical "
    "tension in the Middle East is keeping a haven bid under gold; ETF holdings rose."
)
_DEMO_INDICATORS = [
    {"name": "CPI YoY", "value": 3.1, "prior": 3.4, "surprise": -0.3},
    {"name": "Core PPI MoM", "value": 0.1, "prior": 0.3, "surprise": -0.2},
    {"name": "Unemployment Rate", "value": 4.1, "prior": 3.9, "surprise": 0.2},
    {"name": "US10Y", "value": 4.18, "prior": 4.30, "surprise": -0.12},
    {"name": "DXY", "value": 103.2, "prior": 104.6, "surprise": -1.4},
]
_DEMO_HEADLINES = [
    {"title": "Gold extends gains as cooler US inflation revives Fed rate-cut bets", "source": "Reuters"},
    {"title": "Dollar slips, Treasury yields fall after soft CPI print", "source": "Bloomberg"},
    {"title": "Safe-haven demand firm as Middle East tensions escalate", "source": "Financial Times"},
    {"title": "Gold ETF holdings climb to a multi-month high on dovish Fed repricing", "source": "Reuters"},
    {"title": "Fed's officials signal patience, opening door to summer rate cut", "source": "Bloomberg"},
]


def build_demo_llm_context(
    *,
    as_of: datetime | None = None,
    drift: float = 0.00016,
    volatility: float = 0.0008,
    seed: int | None = 11,
    equity: float = 100_000.0,
    render_chart: bool = True,
    minutes_to_event: int = 180,
) -> MarketContext:
    """A synthetic context **enriched with macro/news/chart inputs** so the three
    LLM-backed agents (Macro, News & Sentiment, Chart Vision) actually run instead
    of abstaining for lack of data.

    This is demo wiring, not a live feed (real feeds are roadmap milestone M1) — it
    lets a single OpenAI/Anthropic key light up the full agent suite end-to-end. The
    scheduled event is placed ``minutes_to_event`` ahead (default 180) so the news
    event-gate is exercised without forcing a blackout veto.
    """
    ctx = build_synthetic_context(
        as_of=as_of, drift=drift, volatility=volatility, seed=seed, equity=equity,
    )
    event_at = (ctx.as_of if ctx.as_of.tzinfo else ctx.as_of.replace(tzinfo=UTC)) + timedelta(minutes=minutes_to_event)
    raw: dict[str, object] = {
        "macro": {
            "digest": _DEMO_DIGEST,
            "indicators": _DEMO_INDICATORS,
            "dxy_trend": "bearish",
            "yields_trend": "bearish",
            "risk_environment": "risk_off",
        },
        "headlines": _DEMO_HEADLINES,
        "calendar": [
            {"title": "FOMC Rate Decision", "importance": "high", "scheduled_at": event_at.isoformat()},
        ],
    }

    screenshot_path: str | None = None
    if render_chart:
        from goldmind.backtest.chart_render import render_candles

        screenshot_path = render_candles(ctx.candles[Timeframe.H1], title="XAUUSD H1 (demo)")

    return MarketContext(
        symbol=ctx.symbol, as_of=ctx.as_of, candles=ctx.candles, account=ctx.account,
        screenshot_path=screenshot_path, raw=raw,
    )
