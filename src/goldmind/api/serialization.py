"""Domain -> JSON serialization for the API.

The dashboard consumes a stable contract; keeping the mapping here (not scattered
across route handlers) makes that contract explicit and testable.
"""

from __future__ import annotations

from typing import Any

from goldmind.core.schemas import AgentOutput, MarketRegimeOutput, RiskAssessment


def serialize_agent(output: AgentOutput) -> dict[str, Any]:
    return {
        "agent": output.agent.value,
        "bias": output.bias.value,
        "confidence": output.confidence,
        "reasoning": output.reasoning,
        "risk_flags": [f.model_dump(mode="json") for f in output.risk_flags],
        "model": output.model,
        "latency_ms": output.latency_ms,
        "error": output.error,
    }


def serialize_regime(regime: MarketRegimeOutput) -> dict[str, Any]:
    return {
        "trend_regime": regime.trend_regime.value,
        "phase_regime": regime.phase_regime.value,
        "volatility_regime": regime.volatility_regime.value,
        "adx": regime.adx,
        "quality_multiplier": regime.quality_multiplier,
        "recommended_behavior": regime.recommended_behavior,
        "confidence": regime.confidence,
    }


def serialize_evaluation(result) -> dict[str, Any]:
    """Full EvaluationResult -> the /evaluate response shape."""
    risk: RiskAssessment = result.risk
    agents = [serialize_agent(o) for o in result.outputs.values()]
    agents.append(serialize_agent(risk))  # include the risk manager as an agent row
    return {
        "as_of": result.ctx.as_of.isoformat(),
        "symbol": result.ctx.symbol,
        "decision": result.decision.model_dump(mode="json"),
        "regime": serialize_regime(result.regime),
        "risk": {
            "approved": risk.approved,
            "rejection_reason": risk.rejection_reason,
            "circuit_breaker_active": risk.circuit_breaker_active,
            "sizing": risk.sizing.model_dump(mode="json") if risk.sizing else None,
        },
        "agents": agents,
    }
