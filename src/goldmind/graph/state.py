"""LangGraph state definition.

The six analytical agents run as parallel nodes that all write into a single
``outputs`` map. Concurrent writes to the same state key require a *reducer* so
LangGraph knows how to merge them — here a shallow dict-merge. Everything else is
written by exactly one node, so it uses last-value semantics.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from goldmind.core.context import MarketContext
from goldmind.core.enums import AgentName
from goldmind.core.schemas import (
    AgentOutput,
    MarketRegimeOutput,
    RiskAssessment,
    TradingDecision,
)


def merge_outputs(
    left: dict[AgentName, AgentOutput] | None,
    right: dict[AgentName, AgentOutput] | None,
) -> dict[AgentName, AgentOutput]:
    """Reducer for the parallel analytical fan-in."""
    return {**(left or {}), **(right or {})}


class GraphState(TypedDict, total=False):
    # input
    ctx: MarketContext
    # fan-in from the six analytical agents
    outputs: Annotated[dict[AgentName, AgentOutput], merge_outputs]
    # single-writer downstream results
    regime: MarketRegimeOutput
    risk: RiskAssessment
    decision: TradingDecision
