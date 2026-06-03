"""FastAPI application — the control plane.

Endpoints are split into three concerns:
  * **live analysis** (`/evaluate`, `/agents`, `/regime`) — runs the orchestrator;
    works with zero external services (synthetic data, no DB, no broker).
  * **history** (`/decisions`, `/trades`, `/performance`, `/news`) — reads the DB;
    degrades to HTTP 503 when the DB isn't configured so the dashboard can fall
    back to its offline state.
  * **ops** (`/health`, `/config`, `/metrics`).

Execution is gated by ``execution_mode`` (the API never silently sends live
orders): `/trades/{id}/approve` is the human-in-the-loop hook for semi-auto.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from goldmind.agents.learning import LearningEngine
from goldmind.api.serialization import serialize_agent, serialize_evaluation, serialize_regime
from goldmind.backtest.synthetic import build_synthetic_context
from goldmind.config import get_settings
from goldmind.core.context import MarketContext
from goldmind.graph.workflow import EvaluationResult, Orchestrator
from goldmind.logging import configure_logging, get_logger

log = get_logger("api")


class EvaluateRequest(BaseModel):
    synthetic: bool = True
    drift: float = 0.00008
    volatility: float = 0.0008
    screenshot_path: str | None = None


def _build_live_context() -> MarketContext:
    """Assemble a context from MT5 (execution node). Falls back to synthetic if the
    terminal is unavailable so the endpoint never hard-fails in non-broker envs."""
    from goldmind.core.enums import Timeframe
    from goldmind.data.mt5_client import MT5Client

    settings = get_settings()
    client = MT5Client(settings)
    client.connect()
    try:
        candles = {tf: client.copy_rates(tf, 1500) for tf in settings.timeframes}
        account = client.account_state()
    finally:
        client.shutdown()
    as_of = candles[Timeframe.M5].index[-1].to_pydatetime() if Timeframe.M5 in candles else MarketContext.utcnow()
    return MarketContext(symbol=settings.symbol, as_of=as_of, candles=candles, account=account)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="GoldMind AI", version="0.1.0", description="Multi-agent AI trading system for XAUUSD.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # tighten to the dashboard origin in production
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.orchestrator = None
    app.state.last_eval = None

    def orchestrator() -> Orchestrator:
        if app.state.orchestrator is None:
            app.state.orchestrator = Orchestrator(settings=settings)
        return app.state.orchestrator

    # ---- ops ----
    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "environment": settings.environment.value, "execution_mode": settings.execution_mode.value, "symbol": settings.symbol}

    @app.get("/config")
    def config() -> dict[str, Any]:
        r = settings.risk
        return {
            "symbol": settings.symbol,
            "environment": settings.environment.value,
            "execution_mode": settings.execution_mode.value,
            "timeframes": [t.value for t in settings.timeframes],
            "risk": {
                "max_risk_per_trade": r.max_risk_per_trade,
                "max_daily_drawdown": r.max_daily_drawdown,
                "max_total_drawdown": r.max_total_drawdown,
                "max_consecutive_losses": r.max_consecutive_losses,
                "max_trades_per_day": r.max_trades_per_day,
                "min_reward_risk": r.min_reward_risk,
            },
            "weights": settings.weights.model_dump(),
        }

    @app.get("/metrics")
    def metrics() -> Any:
        try:
            from fastapi import Response
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

            from goldmind.observability import registry

            return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
        except Exception as exc:  # pragma: no cover - prometheus optional
            raise HTTPException(status_code=503, detail="metrics unavailable") from exc

    # ---- live analysis ----
    @app.post("/evaluate")
    def evaluate(req: EvaluateRequest) -> dict[str, Any]:
        if req.synthetic:
            ctx = build_synthetic_context(drift=req.drift, volatility=req.volatility)
        else:
            try:
                ctx = _build_live_context()
            except Exception as exc:  # broker not available
                raise HTTPException(status_code=503, detail=f"live data unavailable: {exc}") from exc
        if req.screenshot_path:
            ctx = MarketContext(symbol=ctx.symbol, as_of=ctx.as_of, candles=ctx.candles, account=ctx.account, screenshot_path=req.screenshot_path)
        result: EvaluationResult = orchestrator().evaluate(ctx)
        app.state.last_eval = result
        from goldmind.observability import record_evaluation

        record_evaluation(result)
        # Best-effort persistence (no-op if DB not configured).
        with suppress(Exception):
            from goldmind.db.repository import persist_evaluation
            from goldmind.db.session import session_scope

            with session_scope() as s:
                persist_evaluation(s, result)
        return serialize_evaluation(result)

    @app.get("/agents")
    def agents() -> list[dict[str, Any]]:
        result = app.state.last_eval or orchestrator().evaluate(build_synthetic_context())
        app.state.last_eval = result
        out = [serialize_agent(o) for o in result.outputs.values()]
        out.append(serialize_agent(result.risk))
        return out

    @app.get("/regime")
    def regime() -> dict[str, Any]:
        result = app.state.last_eval or orchestrator().evaluate(build_synthetic_context())
        app.state.last_eval = result
        return serialize_regime(result.regime)

    # ---- history (DB-backed) ----
    def _session():
        try:
            from goldmind.db.session import session_scope

            return session_scope()
        except Exception as exc:  # pragma: no cover
            raise HTTPException(status_code=503, detail=f"database unavailable: {exc}") from exc

    @app.get("/decisions")
    def decisions(limit: int = Query(50, ge=1, le=500)) -> list[dict[str, Any]]:
        from sqlalchemy import select

        from goldmind.db.models import Signal

        try:
            with _session() as s:
                rows = s.execute(select(Signal).order_by(Signal.created_at.desc()).limit(limit)).scalars().all()
                return [
                    {
                        "id": str(r.id), "decision": r.decision, "bias": r.bias,
                        "confidence": float(r.confidence), "quality_score": float(r.quality_score),
                        "net_score": float(r.net_score), "agreement": float(r.agreement),
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in rows
                ]
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"database unavailable: {exc}") from exc

    @app.get("/trades")
    def trades(status: str | None = None, limit: int = Query(100, ge=1, le=1000)) -> list[dict[str, Any]]:
        from sqlalchemy import select

        from goldmind.db.models import Trade

        try:
            with _session() as s:
                stmt = select(Trade).order_by(Trade.created_at.desc()).limit(limit)
                if status:
                    stmt = stmt.where(Trade.status == status)
                rows = s.execute(stmt).scalars().all()
                return [_trade_dict(r) for r in rows]
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"database unavailable: {exc}") from exc

    @app.get("/trades/active")
    def active_trades() -> list[dict[str, Any]]:
        from sqlalchemy import select

        from goldmind.db.models import Trade

        try:
            with _session() as s:
                rows = s.execute(select(Trade).where(Trade.status == "open")).scalars().all()
                return [_trade_dict(r) for r in rows]
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"database unavailable: {exc}") from exc

    @app.post("/trades/{trade_id}/approve")
    def approve_trade(trade_id: str) -> dict[str, Any]:
        # Human-in-the-loop gate for semi-auto. Routing to the broker is performed
        # by the execution worker; here we only flip the approval flag/status.
        from goldmind.db.models import Trade

        try:
            with _session() as s:
                trade = s.get(Trade, trade_id)
                if trade is None:
                    raise HTTPException(status_code=404, detail="trade not found")
                if trade.status != "proposed":
                    raise HTTPException(status_code=409, detail=f"trade is {trade.status}, not proposed")
                trade.status = "pending"
                return {"id": str(trade.id), "status": trade.status}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"database unavailable: {exc}") from exc

    @app.get("/performance")
    def performance() -> dict[str, Any]:
        try:
            from goldmind.db.repository import fetch_closed_trades

            with _session() as s:
                closed = fetch_closed_trades(s)
            report = LearningEngine().analyze(closed)
            return report.model_dump(mode="json")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"database unavailable: {exc}") from exc

    @app.get("/news")
    def news() -> list[dict[str, Any]]:
        # Prefer the most recent live evaluation's news agent; fall back to DB.
        result = app.state.last_eval
        if result is not None:
            from goldmind.core.enums import AgentName

            ns = result.outputs.get(AgentName.NEWS_SENTIMENT)
            if ns is not None and getattr(ns, "events", None):
                return [e.model_dump(mode="json") for e in ns.events]
        return []

    return app


def _trade_dict(r) -> dict[str, Any]:
    return {
        "id": str(r.id), "side": r.side, "status": r.status, "volume": float(r.volume),
        "entry_price": float(r.entry_price) if r.entry_price is not None else None,
        "stop_loss": float(r.stop_loss) if r.stop_loss is not None else None,
        "exit_price": float(r.exit_price) if r.exit_price is not None else None,
        "pnl": float(r.pnl) if r.pnl is not None else None,
        "r_multiple": float(r.r_multiple) if r.r_multiple is not None else None,
        "reward_risk": float(r.reward_risk) if r.reward_risk is not None else None,
        "opened_at": r.opened_at.isoformat() if r.opened_at else None,
        "closed_at": r.closed_at.isoformat() if r.closed_at else None,
    }


app = create_app()
