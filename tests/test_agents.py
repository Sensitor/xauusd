"""Analytical agents produce sensible, direction-consistent reads on synthetic data."""

from __future__ import annotations

from goldmind.agents.market_regime import MarketRegimeAgent
from goldmind.agents.market_structure import MarketStructureAgent
from goldmind.agents.technical import TechnicalAgent
from goldmind.core.enums import TrendRegime


def test_technical_separates_trends(uptrend_ctx, downtrend_ctx):
    up = TechnicalAgent().run(uptrend_ctx)
    down = TechnicalAgent().run(downtrend_ctx)
    assert up.error is None and down.error is None
    assert up.bullish_bearish_score > down.bullish_bearish_score
    assert 0.0 <= up.indicator_alignment_score <= 1.0


def test_structure_alignment_follows_trend(uptrend_ctx, downtrend_ctx):
    up = MarketStructureAgent().run(uptrend_ctx)
    down = MarketStructureAgent().run(downtrend_ctx)
    assert up.mtf_alignment > down.mtf_alignment
    assert up.timeframe_trends  # populated per timeframe


def test_regime_classifies_trend(uptrend_ctx, downtrend_ctx, chop_ctx):
    assert MarketRegimeAgent().run(uptrend_ctx).trend_regime is TrendRegime.TRENDING_UP
    assert MarketRegimeAgent().run(downtrend_ctx).trend_regime is TrendRegime.TRENDING_DOWN
    assert MarketRegimeAgent().run(chop_ctx).trend_regime is TrendRegime.RANGING


def test_regime_quality_multiplier_in_chop(chop_ctx):
    out = MarketRegimeAgent().run(chop_ctx)
    assert out.quality_multiplier > 1.0  # ranging demands more conviction


def test_llm_agents_degrade_without_keys(uptrend_ctx):
    # Macro/News/Vision must abstain cleanly (no crash) when no LLM/data is present.
    from goldmind.agents.chart_vision import ChartVisionAgent
    from goldmind.agents.macro import MacroAgent
    from goldmind.agents.news_sentiment import NewsSentimentAgent

    for agent in (MacroAgent(), NewsSentimentAgent(), ChartVisionAgent()):
        out = agent.run(uptrend_ctx)
        assert 0.0 <= out.confidence <= 1.0
        assert out.latency_ms is not None
