"""The orchestration layer.

Two entry points, one set of node functions:

* :class:`Orchestrator` — a direct, synchronous pipeline used by the backtester,
  tests, and any caller that just wants ``ctx -> decision`` with minimal overhead.
  The six analytical agents run concurrently in a thread pool (their work is
  I/O-bound LLM calls or fast numpy), then the risk gate, then the decision.
* :func:`build_workflow` — the same logic expressed as a LangGraph ``StateGraph``
  (parallel fan-out -> risk -> decision). This is the production runtime: it gives
  streaming, checkpointing, retries and a visual graph for free.

Pipeline:  START ─▶ [structure, technical, macro, news, vision, regime] ─▶ risk ─▶ decision ─▶ END
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from goldmind.agents.decision_engine import provisional_direction
from goldmind.agents.registry import AgentSuite, build_suite
from goldmind.config import Settings, get_settings
from goldmind.core.context import MarketContext
from goldmind.core.enums import AgentName, Timeframe
from goldmind.core.schemas import (
    AgentOutput,
    MarketRegimeOutput,
    RiskAssessment,
    TradingDecision,
)
from goldmind.graph.state import GraphState
from goldmind.indicators.technical import atr as atr_indicator
from goldmind.logging import get_logger

log = get_logger("orchestrator")


@dataclass
class EvaluationResult:
    """Everything produced in one cycle — the unit the persistence layer stores."""

    ctx: MarketContext
    outputs: dict[AgentName, AgentOutput]
    regime: MarketRegimeOutput
    risk: RiskAssessment
    decision: TradingDecision

    @property
    def reference_atr(self) -> float | None:
        return self.risk.sizing.stop_distance / get_settings().risk.default_atr_stop_mult if self.risk.sizing else None


# --------------------------------------------------------------------------
# Shared node logic (used by both the Orchestrator and the LangGraph nodes)
# --------------------------------------------------------------------------
def _reference_entry_atr(ctx: MarketContext) -> tuple[float, float]:
    """Execution entry (lowest available TF close) and a robust ATR (H1 preferred)."""
    exec_tf = Timeframe.M5 if ctx.has(Timeframe.M5) else (Timeframe.M15 if ctx.has(Timeframe.M15) else Timeframe.H1)
    entry = ctx.last_close(exec_tf)

    atr_tf = Timeframe.H1 if ctx.has(Timeframe.H1) else exec_tf
    df = ctx.frame(atr_tf)
    atr_series = atr_indicator(df["high"], df["low"], df["close"])
    atr_val = float(atr_series.iloc[-1]) if len(atr_series) and atr_series.iloc[-1] == atr_series.iloc[-1] else 0.0
    if atr_val <= 0:  # degenerate fallback: 0.1% of price
        atr_val = entry * 0.001
    return entry, atr_val


def run_analytical(suite: AgentSuite, ctx: MarketContext, *, concurrent: bool = True) -> dict[AgentName, AgentOutput]:
    agents = list(suite.analytical.values())
    if concurrent and len(agents) > 1:
        with ThreadPoolExecutor(max_workers=len(agents)) as pool:
            results = list(pool.map(lambda a: a.run(ctx), agents))
    else:
        results = [a.run(ctx) for a in agents]
    return {o.agent: o for o in results}


def run_risk(suite: AgentSuite, ctx: MarketContext, outputs: dict[AgentName, AgentOutput]) -> RiskAssessment:
    direction, _net = provisional_direction(outputs, suite.decision_engine.settings)
    entry, atr_val = _reference_entry_atr(ctx)
    return suite.risk_manager.assess(ctx, direction, entry, atr_val)


def run_decision(
    suite: AgentSuite, ctx: MarketContext, outputs: dict[AgentName, AgentOutput], risk: RiskAssessment
) -> TradingDecision:
    regime = outputs.get(AgentName.MARKET_REGIME)
    regime_typed = regime if isinstance(regime, MarketRegimeOutput) else None
    return suite.decision_engine.decide(ctx.symbol, outputs, risk, regime_typed)


# --------------------------------------------------------------------------
# Orchestrator (direct pipeline)
# --------------------------------------------------------------------------
class Orchestrator:
    def __init__(self, suite: AgentSuite | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.suite = suite or build_suite(self.settings)

    def evaluate(self, ctx: MarketContext, *, concurrent: bool = True) -> EvaluationResult:
        ctx.validate()
        outputs = run_analytical(self.suite, ctx, concurrent=concurrent)
        risk = run_risk(self.suite, ctx, outputs)
        decision = run_decision(self.suite, ctx, outputs, risk)
        regime = outputs.get(AgentName.MARKET_REGIME)
        return EvaluationResult(
            ctx=ctx,
            outputs=outputs,
            regime=regime if isinstance(regime, MarketRegimeOutput) else MarketRegimeOutput(agent=AgentName.MARKET_REGIME),
            risk=risk,
            decision=decision,
        )


# --------------------------------------------------------------------------
# LangGraph workflow
# --------------------------------------------------------------------------
def build_workflow(suite: AgentSuite | None = None, settings: Settings | None = None):
    """Compile and return the LangGraph application (``.invoke({'ctx': ctx})``)."""
    from langgraph.graph import END, START, StateGraph  # lazy: keep core import light

    s = settings or get_settings()
    suite = suite or build_suite(s)
    g: StateGraph = StateGraph(GraphState)

    def make_analytical_node(agent):
        def _node(state: GraphState) -> dict:
            return {"outputs": {agent.name: agent.run(state["ctx"])}}
        return _node

    for name, agent in suite.analytical.items():
        g.add_node(name.value, make_analytical_node(agent))
        g.add_edge(START, name.value)
        g.add_edge(name.value, "risk")

    def risk_node(state: GraphState) -> dict:
        outputs = state["outputs"]
        risk = run_risk(suite, state["ctx"], outputs)
        regime = outputs.get(AgentName.MARKET_REGIME)
        return {"risk": risk, "regime": regime}

    def decision_node(state: GraphState) -> dict:
        return {"decision": run_decision(suite, state["ctx"], state["outputs"], state["risk"])}

    g.add_node("risk", risk_node)
    g.add_node("decision", decision_node)
    g.add_edge("risk", "decision")
    g.add_edge("decision", END)
    return g.compile()


def _print_mermaid() -> None:
    try:
        app = build_workflow()
        print(app.get_graph().draw_mermaid())
    except Exception as exc:  # pragma: no cover - depends on langgraph version
        # Fallback static diagram so `make graph` always yields something useful.
        print(
            "flowchart TD\n"
            "  START([start]) --> MS[market_structure] & TE[technical] & MA[macro] & NE[news_sentiment] & VI[chart_vision] & RG[market_regime]\n"
            "  MS & TE & MA & NE & VI & RG --> RISK[risk_manager]\n"
            "  RISK --> DEC[decision_engine] --> END([end])\n"
            f"  %% (live render unavailable: {exc})"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="GoldMind workflow utilities")
    parser.add_argument("--print-mermaid", action="store_true", help="Print the LangGraph as mermaid")
    args = parser.parse_args()
    if args.print_mermaid:
        _print_mermaid()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
