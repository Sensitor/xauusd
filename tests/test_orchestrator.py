"""End-to-end orchestration on synthetic data."""

from __future__ import annotations

from goldmind.core.enums import SCORING_AGENTS, TradeDecision
from goldmind.graph.workflow import Orchestrator


def test_evaluate_returns_complete_result(uptrend_ctx):
    res = Orchestrator().evaluate(uptrend_ctx, concurrent=False)
    # All six analytical voters present.
    for agent in SCORING_AGENTS:
        assert agent in res.outputs
    assert res.decision.decision in (TradeDecision.BUY, TradeDecision.SELL, TradeDecision.NO_TRADE)
    assert res.decision.reasoning
    assert -1.0 <= res.decision.net_directional_score <= 1.0
    assert 0.0 <= res.decision.quality_score <= 100.0


def test_trade_decisions_carry_sizing(downtrend_ctx):
    res = Orchestrator().evaluate(downtrend_ctx, concurrent=False)
    if res.decision.decision in (TradeDecision.BUY, TradeDecision.SELL):
        assert res.risk.approved
        assert res.decision.sizing is not None
        assert res.decision.sizing.lot_size > 0
        assert res.decision.sizing.reward_risk > 0


def test_no_trade_has_no_sizing(chop_ctx):
    res = Orchestrator().evaluate(chop_ctx, concurrent=False)
    if res.decision.decision is TradeDecision.NO_TRADE:
        assert res.decision.sizing is None


def test_concurrent_matches_sequential(uptrend_ctx):
    seq = Orchestrator().evaluate(uptrend_ctx, concurrent=False).decision
    con = Orchestrator().evaluate(uptrend_ctx, concurrent=True).decision
    assert seq.decision is con.decision
    assert seq.net_directional_score == con.net_directional_score
