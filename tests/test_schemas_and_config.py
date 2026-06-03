"""Validation guarantees on the contracts and config (fail-fast on bad values)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from goldmind.config import DecisionWeights, RiskConfig
from goldmind.core.enums import AgentName, Bias
from goldmind.core.schemas import AccountState, AgentOutput


def test_confidence_must_be_unit_interval():
    with pytest.raises(ValidationError):
        AgentOutput(agent=AgentName.TECHNICAL, confidence=1.5)
    with pytest.raises(ValidationError):
        AgentOutput(agent=AgentName.TECHNICAL, confidence=-0.1)


def test_signed_confidence():
    o = AgentOutput(agent=AgentName.MACRO, bias=Bias.BEARISH, confidence=0.5)
    assert o.signed_confidence == -0.5


def test_riskconfig_partials_must_sum_to_one():
    with pytest.raises(ValidationError):
        RiskConfig(tp_r_multiples=[1.5, 2.5], tp_partials=[0.5, 0.4])


def test_riskconfig_daily_below_total():
    with pytest.raises(ValidationError):
        RiskConfig(max_daily_drawdown=0.08, max_total_drawdown=0.06)


def test_decision_weights_must_sum_to_one():
    with pytest.raises(ValidationError):
        DecisionWeights(market_structure=0.9)


def test_scoring_weights_renormalize_without_risk():
    w = DecisionWeights().scoring_weights()
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert AgentName.RISK_MANAGER not in w


def test_account_drawdown_and_daily_pct():
    acct = AccountState(equity=95_000, balance=95_000, peak_equity=100_000, daily_realized_pnl=-5_000)
    assert acct.drawdown_pct == pytest.approx(0.05)
    assert acct.daily_pnl_pct == pytest.approx(-0.05)
