"""Learning Engine statistics and insight generation."""

from __future__ import annotations

from datetime import datetime, timedelta

from goldmind.agents.learning import ClosedTrade, LearningEngine
from goldmind.core.enums import OrderSide


def _trade(i: int, r: float, regime: str = "trending_up", agreement: float = 0.8) -> ClosedTrade:
    t0 = datetime(2026, 1, 1) + timedelta(hours=i)
    return ClosedTrade(id=str(i), opened_at=t0, closed_at=t0 + timedelta(hours=2),
                       side=OrderSide.BUY, r_multiple=r, pnl=r * 500, regime=regime,
                       agreement=agreement, hour=t0.hour)


def test_metrics_on_known_ledger():
    # 3 wins of +2R, 2 losses of -1R.
    trades = [_trade(i, 2.0) for i in range(3)] + [_trade(i + 3, -1.0) for i in range(2)]
    rep = LearningEngine().analyze(trades)
    assert rep.trades == 5
    assert rep.win_rate == 0.6
    assert rep.profit_factor == 3.0  # 6 / 2
    assert abs(rep.expectancy_r - 0.8) < 1e-6
    assert rep.avg_win_r == 2.0 and rep.avg_loss_r == -1.0
    assert rep.max_drawdown_r is not None


def test_empty_ledger_is_safe():
    rep = LearningEngine().analyze([])
    assert rep.trades == 0 and rep.expectancy_r == 0.0


def test_negative_expectancy_triggers_insight():
    trades = [_trade(i, -0.5) for i in range(15)]
    rep = LearningEngine().analyze(trades)
    assert rep.expectancy_r < 0
    assert any(i.category in ("selection", "filter") for i in rep.insights)


def test_low_agreement_underperformance_insight():
    good = [_trade(i, 1.5, agreement=0.85) for i in range(10)]
    bad = [_trade(i + 10, -0.8, agreement=0.4) for i in range(10)]
    rep = LearningEngine().analyze(good + bad)
    assert any("agreement" in i.statement.lower() for i in rep.insights)
