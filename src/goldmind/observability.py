"""Prometheus metrics.

Import-safe: if ``prometheus_client`` is not installed the module still imports and
every recorder becomes a no-op, so the core never hard-depends on the metrics
stack. The Grafana dashboards in ``deploy/`` are built against these series.
"""

from __future__ import annotations

from typing import Any

try:
    from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

    registry = CollectorRegistry()
    _ENABLED = True
except Exception:  # pragma: no cover - metrics optional
    registry = None  # type: ignore[assignment]
    _ENABLED = False


if _ENABLED:
    EVALUATIONS = Counter("goldmind_evaluations_total", "Evaluation cycles", ["decision"], registry=registry)
    AGENT_LATENCY = Histogram("goldmind_agent_latency_seconds", "Per-agent latency", ["agent"], registry=registry,
                              buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))
    DECISION_QUALITY = Histogram("goldmind_decision_quality", "Decision quality score (0-100)", registry=registry,
                                 buckets=(0, 20, 40, 50, 60, 70, 80, 90, 100))
    TRADES = Counter("goldmind_trades_total", "Trades by side/outcome", ["side", "outcome"], registry=registry)
    EQUITY = Gauge("goldmind_account_equity", "Account equity", registry=registry)
    DRAWDOWN = Gauge("goldmind_account_drawdown_pct", "Account drawdown fraction", registry=registry)
    CIRCUIT_BREAKER = Counter("goldmind_circuit_breaker_trips_total", "Circuit-breaker trips", ["rule"], registry=registry)


def record_evaluation(result: Any) -> None:
    """Update metrics from an EvaluationResult (best-effort, never raises)."""
    if not _ENABLED:
        return
    try:
        EVALUATIONS.labels(decision=result.decision.decision.value).inc()
        DECISION_QUALITY.observe(float(result.decision.quality_score))
        for out in result.outputs.values():
            if out.latency_ms is not None:
                AGENT_LATENCY.labels(agent=out.agent.value).observe(out.latency_ms / 1000.0)
        if result.risk.account is not None:
            EQUITY.set(float(result.risk.account.equity))
            DRAWDOWN.set(float(result.risk.account.drawdown_pct))
        if result.risk.circuit_breaker_active:
            CIRCUIT_BREAKER.labels(rule="circuit_breaker").inc()
    except Exception:  # pragma: no cover - metrics must never break trading
        pass


def record_trade_closed(side: str, r_multiple: float) -> None:
    if not _ENABLED:
        return
    with_suppress = TRADES.labels(side=side, outcome="win" if r_multiple > 0 else "loss")
    with_suppress.inc()
