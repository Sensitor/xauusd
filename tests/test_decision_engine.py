"""Decision Engine: weighted vote, gating, and hard vetoes."""

from __future__ import annotations

from goldmind.agents.decision_engine import DecisionEngine, provisional_direction
from goldmind.agents.risk_manager import RiskManager
from goldmind.config import Settings
from goldmind.core.enums import AgentName, Bias, Severity, TradeDecision
from goldmind.core.schemas import (
    ChartVisionOutput,
    MacroOutput,
    MarketRegimeOutput,
    MarketStructureOutput,
    NewsSentimentOutput,
    RiskAssessment,
    RiskFlag,
    TechnicalOutput,
)

S = Settings()


def _bullish_outputs(conf: float = 0.8) -> dict[AgentName, object]:
    return {
        AgentName.MARKET_STRUCTURE: MarketStructureOutput(bias=Bias.BULLISH, confidence=conf, structural_bias=Bias.BULLISH),
        AgentName.TECHNICAL: TechnicalOutput(bias=Bias.BULLISH, confidence=conf, bullish_bearish_score=0.6),
        AgentName.MACRO: MacroOutput(bias=Bias.BULLISH, confidence=0.6, macro_bias=Bias.BULLISH),
        AgentName.NEWS_SENTIMENT: NewsSentimentOutput(bias=Bias.NEUTRAL, confidence=0.0),
        AgentName.CHART_VISION: ChartVisionOutput(bias=Bias.BULLISH, confidence=0.6, detected_trend=Bias.BULLISH),
        AgentName.MARKET_REGIME: MarketRegimeOutput(bias=Bias.BULLISH, confidence=0.8, quality_multiplier=1.0),
    }


def _approved_risk(side: Bias) -> RiskAssessment:
    sizing = RiskManager(S).size("XAUUSD", side, entry=2350.0, atr=5.0, equity=100_000.0)
    return RiskAssessment(approved=True, confidence=1.0, sizing=sizing)


def test_provisional_direction_bullish():
    direction, net = provisional_direction(_bullish_outputs(), S)
    assert direction is Bias.BULLISH and net > 0


def test_strong_aligned_setup_buys():
    outputs = _bullish_outputs(0.85)
    decision = DecisionEngine(S).decide("XAUUSD", outputs, _approved_risk(Bias.BULLISH), outputs[AgentName.MARKET_REGIME])
    assert decision.decision is TradeDecision.BUY
    assert decision.quality_score >= 60
    assert decision.sizing is not None


def test_risk_rejection_forces_no_trade():
    outputs = _bullish_outputs(0.85)
    rejected = RiskAssessment(approved=False, rejection_reason="circuit breaker")
    decision = DecisionEngine(S).decide("XAUUSD", outputs, rejected, outputs[AgentName.MARKET_REGIME])
    assert decision.decision is TradeDecision.NO_TRADE


def test_news_blackout_vetoes_strong_setup():
    outputs = _bullish_outputs(0.9)
    outputs[AgentName.NEWS_SENTIMENT].risk_flags.append(
        RiskFlag(code="news_blackout", message="FOMC in 5m", severity=Severity.CRITICAL, source=AgentName.NEWS_SENTIMENT)
    )
    decision = DecisionEngine(S).decide("XAUUSD", outputs, _approved_risk(Bias.BULLISH), outputs[AgentName.MARKET_REGIME])
    assert decision.decision is TradeDecision.NO_TRADE
    assert "veto" in decision.reasoning.lower()


def test_conflict_produces_no_trade():
    outputs = _bullish_outputs(0.8)
    outputs[AgentName.TECHNICAL] = TechnicalOutput(bias=Bias.BEARISH, confidence=0.8)
    outputs[AgentName.MARKET_STRUCTURE] = MarketStructureOutput(bias=Bias.BEARISH, confidence=0.8, structural_bias=Bias.BEARISH)
    decision = DecisionEngine(S).decide("XAUUSD", outputs, _approved_risk(Bias.BULLISH), outputs[AgentName.MARKET_REGIME])
    assert decision.decision is TradeDecision.NO_TRADE


def test_regime_multiplier_raises_the_bar():
    """A chop multiplier > 1 can turn a marginal BUY into NO_TRADE."""
    outputs = _bullish_outputs(0.62)
    permissive = MarketRegimeOutput(bias=Bias.BULLISH, confidence=0.5, quality_multiplier=1.0)
    strict = MarketRegimeOutput(bias=Bias.BULLISH, confidence=0.5, quality_multiplier=1.4)
    eng = DecisionEngine(S)
    base = eng.decide("XAUUSD", {**outputs, AgentName.MARKET_REGIME: permissive}, _approved_risk(Bias.BULLISH), permissive)
    raised = eng.decide("XAUUSD", {**outputs, AgentName.MARKET_REGIME: strict}, _approved_risk(Bias.BULLISH), strict)
    # The strict regime must be at least as conservative as the permissive one.
    order = {TradeDecision.BUY: 0, TradeDecision.NO_TRADE: 1, TradeDecision.SELL: 0}
    assert order[raised.decision] >= order[base.decision]
