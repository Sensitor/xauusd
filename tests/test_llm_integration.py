"""LLM provider fallback + the enriched-context path that lets the LLM agents run.

No network and no langchain required: provider resolution is pure, and the agent
paths are exercised with a stubbed ``complete_structured`` so we prove the wiring
(a single key powers every role; the demo context actually feeds the agents)
without calling a real model.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from goldmind.agents.chart_vision import ChartVisionAgent
from goldmind.agents.macro import MacroAgent
from goldmind.agents.news_sentiment import NewsSentimentAgent
from goldmind.backtest.synthetic import build_demo_llm_context
from goldmind.core.context import MarketContext
from goldmind.core.enums import Bias, RiskEnvironment
from goldmind.llm import resolve_model


def _settings(openai=None, anthropic=None):
    return SimpleNamespace(
        openai_api_key=openai,
        anthropic_api_key=anthropic,
        reasoning_model="claude-sonnet-4-6",
        vision_model="gpt-4o",
        fast_model="claude-haiku-4-5-20251001",
        llm_temperature=0.1,
        llm_timeout_s=60,
    )


# --------------------------------------------------------------------------- #
# Provider resolution / fallback
# --------------------------------------------------------------------------- #
def test_openai_only_key_powers_every_role():
    s = _settings(openai="sk-openai")
    assert resolve_model("reasoning", s) == ("openai", "gpt-4o")      # claude default -> openai fallback
    assert resolve_model("fast", s) == ("openai", "gpt-4o-mini")      # haiku default -> openai fallback
    assert resolve_model("vision", s) == ("openai", "gpt-4o")         # already openai


def test_anthropic_only_key_powers_every_role():
    s = _settings(anthropic="sk-anthropic")
    assert resolve_model("reasoning", s) == ("anthropic", "claude-sonnet-4-6")
    assert resolve_model("fast", s) == ("anthropic", "claude-haiku-4-5-20251001")
    assert resolve_model("vision", s) == ("anthropic", "claude-sonnet-4-6")  # gpt default -> anthropic fallback


def test_both_keys_honor_configured_provider():
    s = _settings(openai="o", anthropic="a")
    assert resolve_model("reasoning", s) == ("anthropic", "claude-sonnet-4-6")
    assert resolve_model("vision", s) == ("openai", "gpt-4o")


def test_no_key_resolves_to_none():
    s = _settings()
    assert resolve_model("reasoning", s) == (None, "claude-sonnet-4-6")


# --------------------------------------------------------------------------- #
# Agent paths through the enriched demo context (stubbed model)
# --------------------------------------------------------------------------- #
def _fake_complete(model, schema, system, human, *, image_path=None):
    """Return a valid instance of whichever private *LLM schema is requested."""
    name = schema.__name__
    if name == "_MacroLLM":
        return schema(
            macro_bias=Bias.BULLISH, risk_environment=RiskEnvironment.RISK_OFF,
            dxy_trend=Bias.BEARISH, yields_trend=Bias.BEARISH,
            confidence=0.62, reasoning="Cooler CPI + risk-off haven bid => bullish gold.",
        )
    if name == "_SentimentLLM":
        return schema(sentiment_score=0.55, confidence=0.6, reasoning="Dovish repricing + safe-haven demand.")
    if name == "_VisionLLM":
        return schema(
            detected_trend=Bias.BULLISH, support_levels=[2300.0], resistance_levels=[2400.0],
            risk_areas=["price into prior supply near 2400"], confidence=0.58,
            reasoning="Higher-highs/higher-lows; constructive uptrend.",
        )
    raise AssertionError(f"unexpected schema {name}")


def test_macro_agent_runs_on_enriched_context(monkeypatch):
    import goldmind.agents.macro as mod

    monkeypatch.setattr(mod, "get_chat_model", lambda role, settings=None: object())
    monkeypatch.setattr(mod, "complete_structured", _fake_complete)

    ctx = build_demo_llm_context(render_chart=False)
    out = MacroAgent(settings=_settings(openai="sk-openai")).analyze(ctx)

    assert out.error is None
    assert out.bias is Bias.BULLISH
    assert out.confidence > 0.0
    assert out.model == "gpt-4o"  # resolved via openai fallback, not the configured claude name


def test_news_agent_runs_on_enriched_context(monkeypatch):
    import goldmind.agents.news_sentiment as mod

    monkeypatch.setattr(mod, "get_chat_model", lambda role, settings=None: object())
    monkeypatch.setattr(mod, "complete_structured", _fake_complete)

    ctx = build_demo_llm_context(render_chart=False)
    out = NewsSentimentAgent(settings=_settings(openai="sk-openai")).analyze(ctx)

    assert out.error is None
    assert out.sentiment_score > 0.0
    assert out.bias is Bias.BULLISH
    assert out.model == "gpt-4o-mini"
    assert out.in_blackout_window is False           # demo event is 180 min out
    assert out.minutes_to_next_high_impact is not None


def test_vision_agent_runs_with_screenshot(monkeypatch):
    import goldmind.agents.chart_vision as mod

    monkeypatch.setattr(mod, "get_chat_model", lambda role, settings=None: object())
    monkeypatch.setattr(mod, "complete_structured", _fake_complete)

    base = build_demo_llm_context(render_chart=False)
    ctx = MarketContext(
        symbol=base.symbol, as_of=base.as_of, candles=base.candles, account=base.account,
        screenshot_path="/tmp/does-not-need-to-exist.png", raw=base.raw,
    )
    out = ChartVisionAgent(settings=_settings(openai="sk-openai")).analyze(ctx)

    assert out.error is None
    assert out.bias is Bias.BULLISH
    assert out.model == "gpt-4o"


def test_chart_render_smoke(tmp_path):
    pytest.importorskip("PIL")
    from goldmind.backtest.chart_render import render_candles
    from goldmind.core.enums import Timeframe

    ctx = build_demo_llm_context(render_chart=False)
    path = render_candles(ctx.candles[Timeframe.H1], out_path=tmp_path / "chart.png")
    assert path is not None
    assert (tmp_path / "chart.png").exists()
