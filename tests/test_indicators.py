"""Indicator correctness and — critically — causality (no look-ahead)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from goldmind.core.enums import Timeframe
from goldmind.indicators.technical import (
    atr,
    bollinger,
    compute_snapshot,
    ema,
    rsi,
    swing_points,
)


def test_rsi_bounded(m5_series):
    r = rsi(m5_series["close"]).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_ema_tracks_trend():
    s = pd.Series(np.arange(1, 200, dtype=float))
    e = ema(s, 20).dropna()
    assert e.is_monotonic_increasing
    assert (e < s.loc[e.index]).all()  # EMA lags a rising series


def test_atr_positive(m5_series):
    a = atr(m5_series["high"], m5_series["low"], m5_series["close"]).dropna()
    assert (a > 0).all()


def test_bollinger_ordering(m5_series):
    u, m, lo, w = bollinger(m5_series["close"])
    valid = u.notna()
    assert (u[valid] >= m[valid]).all()
    assert (m[valid] >= lo[valid]).all()
    assert (w.dropna() >= 0).all()


def test_swings_are_causal():
    # The last `right` bars can never be confirmed swings (no repainting).
    df = pd.DataFrame({"high": np.random.default_rng(0).random(100) + 10, "low": np.random.default_rng(1).random(100)})
    is_high, is_low = swing_points(df["high"], df["low"], left=2, right=2)
    assert not is_high.iloc[-2:].any()
    assert not is_low.iloc[-2:].any()


def test_snapshot_has_no_nan_inf(m5_series):
    snap = compute_snapshot(m5_series, Timeframe.M5)
    for field in ("rsi", "ema20", "atr", "close"):
        v = getattr(snap, field)
        assert v is None or np.isfinite(v)
    assert snap.close is not None and snap.close > 0
