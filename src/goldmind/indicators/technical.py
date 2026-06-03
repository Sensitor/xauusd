"""Technical indicators implemented from first principles.

We deliberately avoid a third-party TA dependency for the core indicators:
they are simple, and owning the implementation means we control NaN handling,
the smoothing convention (Wilder vs. EMA), and — crucially for a trading system —
the guarantee that everything is **causal** (no look-ahead). Every function
returns a Series aligned to the input index with NaNs where there is insufficient
history; callers decide how to treat the warm-up period.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from goldmind.core.enums import Bias, Timeframe
from goldmind.core.schemas import IndicatorSnapshot


def _wilder(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing == EMA with alpha = 1/period."""
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI in [0, 100]."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = _wilder(gain, period)
    avg_loss = _wilder(loss, period)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # When average loss is zero, RSI is 100 by definition.
    out = out.where(avg_loss != 0, 100.0)
    return out


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (macd_line, signal_line, histogram)."""
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    return _wilder(true_range(high, low, close), period)


def bollinger(
    close: pd.Series, period: int = 20, mult: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Return (upper, mid, lower, width). ``width`` is normalized by the mid band
    so it is comparable across price levels (used for compression/expansion)."""
    mid = close.rolling(period, min_periods=period).mean()
    std = close.rolling(period, min_periods=period).std(ddof=0)
    upper = mid + mult * std
    lower = mid - mult * std
    width = (upper - lower) / mid
    return upper, mid, lower, width


def adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (adx, plus_di, minus_di). ADX > 25 ~ trending, < 20 ~ ranging."""
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm = pd.Series(plus_dm, index=high.index)
    minus_dm = pd.Series(minus_dm, index=high.index)

    atr_ = atr(high, low, close, period)
    plus_di = 100.0 * _wilder(plus_dm, period) / atr_
    minus_di = 100.0 * _wilder(minus_dm, period) / atr_
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    adx_ = _wilder(dx, period)
    return adx_, plus_di, minus_di


def relative_volume(volume: pd.Series, period: int = 20) -> pd.Series:
    avg = volume.rolling(period, min_periods=max(2, period // 2)).mean()
    return volume / avg.replace(0.0, np.nan)


def swing_points(
    high: pd.Series, low: pd.Series, left: int = 2, right: int = 2
) -> tuple[pd.Series, pd.Series]:
    """Confirmed fractal swing highs/lows (boolean Series).

    A swing high at bar *i* requires ``high[i]`` to be the strict max over
    ``[i-left, i+right]``. Because confirmation needs ``right`` future bars, the
    most recent ``right`` bars can never be swings — this is intentional and keeps
    structure detection strictly causal (no repainting).
    """
    n = len(high)
    is_high = pd.Series(False, index=high.index)
    is_low = pd.Series(False, index=low.index)
    hv = high.values
    lv = low.values
    for i in range(left, n - right):
        window_hi = hv[i - left : i + right + 1]
        window_lo = lv[i - left : i + right + 1]
        if hv[i] == window_hi.max() and (window_hi == hv[i]).sum() == 1:
            is_high.iloc[i] = True
        if lv[i] == window_lo.min() and (window_lo == lv[i]).sum() == 1:
            is_low.iloc[i] = True
    return is_high, is_low


def _f(value: float | np.floating | None) -> float | None:
    """Convert a possibly-NaN numpy scalar to a JSON-safe float|None."""
    if value is None:
        return None
    v = float(value)
    return None if (np.isnan(v) or np.isinf(v)) else round(v, 6)


def compute_snapshot(df: pd.DataFrame, timeframe: Timeframe) -> IndicatorSnapshot:
    """Compute the full indicator set for the most recent *closed* bar."""
    close, high, low = df["close"], df["high"], df["low"]
    volume = df["volume"] if "volume" in df.columns else pd.Series(np.nan, index=df.index)

    rsi_v = rsi(close)
    macd_l, macd_s, macd_h = macd(close)
    e20, e50, e200 = ema(close, 20), ema(close, 50), ema(close, 200)
    atr_v = atr(high, low, close)
    bb_u, bb_m, bb_l, bb_w = bollinger(close)
    relvol = relative_volume(volume)

    last_close = _f(close.iloc[-1])
    atr_last = _f(atr_v.iloc[-1])
    atr_pct = round(atr_last / last_close, 6) if (atr_last and last_close) else None

    return IndicatorSnapshot(
        timeframe=timeframe,
        rsi=_f(rsi_v.iloc[-1]),
        macd=_f(macd_l.iloc[-1]),
        macd_signal=_f(macd_s.iloc[-1]),
        macd_hist=_f(macd_h.iloc[-1]),
        ema20=_f(e20.iloc[-1]),
        ema50=_f(e50.iloc[-1]),
        ema200=_f(e200.iloc[-1]),
        atr=atr_last,
        atr_pct=atr_pct,
        bb_upper=_f(bb_u.iloc[-1]),
        bb_mid=_f(bb_m.iloc[-1]),
        bb_lower=_f(bb_l.iloc[-1]),
        bb_width=_f(bb_w.iloc[-1]),
        rel_volume=_f(relvol.iloc[-1]),
        close=last_close,
    )


def bias_from_snapshot(s: IndicatorSnapshot) -> Bias:
    """Cheap helper: net directional read of a snapshot's EMA stack + momentum."""
    if s.close is None or s.ema50 is None or s.ema200 is None:
        return Bias.NEUTRAL
    score = 0
    score += 1 if s.close > s.ema50 else -1
    score += 1 if s.ema50 > s.ema200 else -1
    if s.macd_hist is not None:
        score += 1 if s.macd_hist > 0 else -1
    if s.rsi is not None:
        score += 1 if s.rsi > 55 else (-1 if s.rsi < 45 else 0)
    if score >= 2:
        return Bias.BULLISH
    if score <= -2:
        return Bias.BEARISH
    return Bias.NEUTRAL
