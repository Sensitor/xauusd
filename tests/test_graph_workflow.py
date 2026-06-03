"""The LangGraph workflow and the direct Orchestrator must agree.

Skipped automatically where langgraph isn't installed (the direct Orchestrator
path is exercised everywhere else); runs in CI where the full stack is present.
"""

from __future__ import annotations

import pytest

pytest.importorskip("langgraph")

from goldmind.backtest.synthetic import build_synthetic_context
from goldmind.graph.workflow import Orchestrator, build_workflow


def test_graph_matches_orchestrator():
    ctx = build_synthetic_context(drift=-0.00018, volatility=0.0007, seed=11)

    direct = Orchestrator().evaluate(ctx, concurrent=False).decision
    app = build_workflow()
    state = app.invoke({"ctx": ctx})
    graph_decision = state["decision"]

    assert graph_decision.decision is direct.decision
    # Net score is deterministic given the same inputs.
    assert abs(graph_decision.net_directional_score - direct.net_directional_score) < 1e-9
    assert set(state["outputs"].keys()) == set(Orchestrator().suite.analytical.keys())


def test_graph_has_expected_nodes():
    app = build_workflow()
    nodes = set(app.get_graph().nodes.keys())
    for expected in ("market_structure", "technical", "macro", "news_sentiment", "chart_vision", "market_regime", "risk", "decision"):
        assert expected in nodes
