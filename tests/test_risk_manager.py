"""Risk Manager: position sizing math and circuit breakers — the capital core."""

from __future__ import annotations

import pytest

from goldmind.agents.risk_manager import CONTRACT_SIZE, RiskManager
from goldmind.config import Settings
from goldmind.core.enums import Bias, OrderSide
from goldmind.core.schemas import AccountState


@pytest.fixture
def rm() -> RiskManager:
    return RiskManager(Settings())


def test_sizing_respects_risk_budget(rm):
    equity = 100_000.0
    sizing = rm.size("XAUUSD", Bias.BULLISH, entry=2350.0, atr=5.0, equity=equity)
    # Risk must not exceed the configured per-trade budget (0.5%).
    assert sizing.risk_pct <= rm.cfg.max_risk_per_trade + 1e-9
    # Lot * stop_distance * contract == cash risked.
    assert sizing.risk_amount == pytest.approx(sizing.lot_size * sizing.stop_distance * CONTRACT_SIZE, rel=1e-6)
    assert sizing.side is OrderSide.BUY
    assert sizing.stop_loss < sizing.entry  # long stop below entry


def test_sizing_short_stop_above_entry(rm):
    sizing = rm.size("XAUUSD", Bias.BEARISH, entry=2350.0, atr=5.0, equity=100_000.0)
    assert sizing.side is OrderSide.SELL
    assert sizing.stop_loss > sizing.entry
    assert sizing.reward_risk >= rm.cfg.min_reward_risk


def test_blended_rr_matches_ladder(rm):
    sizing = rm.size("XAUUSD", Bias.BULLISH, entry=2350.0, atr=5.0, equity=100_000.0)
    expected = sum(r * f for r, f in zip(rm.cfg.tp_r_multiples, rm.cfg.tp_partials, strict=True))
    assert sizing.reward_risk == pytest.approx(round(expected, 2))
    assert sum(tp.close_fraction for tp in sizing.take_profits) == pytest.approx(1.0)


def _acct(**kw) -> AccountState:
    base = {"equity": 100_000.0, "balance": 100_000.0, "peak_equity": 100_000.0}
    base.update(kw)
    return AccountState(**base)


def test_breaker_daily_drawdown(rm):
    acct = _acct(equity=97_500.0, daily_realized_pnl=-2_500.0)  # -2.5% day
    broke, reason, _ = rm.circuit_breaker(acct)
    assert broke and "Daily drawdown" in reason


def test_breaker_total_drawdown(rm):
    acct = _acct(equity=93_000.0, peak_equity=100_000.0)  # -7% from peak
    broke, reason, _ = rm.circuit_breaker(acct)
    assert broke and "Total drawdown" in reason


def test_breaker_consecutive_losses(rm):
    broke, reason, _ = rm.circuit_breaker(_acct(consecutive_losses=3))
    assert broke and "consecutive losses" in reason


def test_breaker_trade_cap(rm):
    broke, reason, _ = rm.circuit_breaker(_acct(trades_today=5))
    assert broke and "trade cap" in reason


def test_breaker_concurrent_positions(rm):
    broke, reason, _ = rm.circuit_breaker(_acct(open_positions=1))
    assert broke and "concurrent positions" in reason


def test_no_breach_passes(rm):
    broke, reason, _ = rm.circuit_breaker(_acct())
    assert not broke and reason is None


def test_assess_rejects_when_breaker_active(rm, downtrend_ctx):
    object.__setattr__(downtrend_ctx, "account", _acct(consecutive_losses=3))
    out = rm.assess(downtrend_ctx, Bias.BEARISH, entry=2350.0, atr=5.0)
    assert not out.approved and out.circuit_breaker_active
    assert any(f.code == "circuit_breaker" for f in out.risk_flags)


def test_assess_rejects_wide_stop_over_budget(rm, uptrend_ctx):
    # An enormous ATR makes even the minimum lot exceed the risk budget.
    out = rm.assess(uptrend_ctx, Bias.BULLISH, entry=2350.0, atr=5000.0)
    assert not out.approved
    assert out.rejection_reason is not None
