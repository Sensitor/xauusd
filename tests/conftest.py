"""Shared fixtures. All tests run offline — no API keys, DB, or broker required."""

from __future__ import annotations

import pytest

from goldmind.backtest.synthetic import build_synthetic_context, generate_ohlcv
from goldmind.config import Settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture
def uptrend_ctx():
    return build_synthetic_context(drift=0.00018, volatility=0.0007, seed=11)


@pytest.fixture
def downtrend_ctx():
    return build_synthetic_context(drift=-0.00018, volatility=0.0007, seed=11)


@pytest.fixture
def chop_ctx():
    # Mean-reverting (ranging) market: low ADX, genuinely sideways.
    return build_synthetic_context(mean_revert=True, volatility=0.0009, seed=3)


@pytest.fixture
def m5_series():
    return generate_ohlcv(2600, drift=0.0001, volatility=0.0008, seed=7)
