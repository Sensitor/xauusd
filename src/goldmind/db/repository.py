"""Persistence repository — the only place that maps domain objects <-> ORM rows.

Centralizing this keeps the agents and orchestrator persistence-agnostic (they can
run with no DB at all) and gives one auditable surface for what we store.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from goldmind.agents.learning import ClosedTrade
from goldmind.core.enums import AgentName, OrderSide, Timeframe
from goldmind.core.schemas import PerformanceReport, PositionSizing, RiskFlag, TradingDecision
from goldmind.db.models import (
    AgentOutputRow,
    MarketSnapshot,
    PerformanceMetric,
    RiskEvent,
    Signal,
    Trade,
)

if TYPE_CHECKING:
    from goldmind.graph.workflow import EvaluationResult

_NEWS_FLAG_CODES = {"news_blackout", "news_proximity"}


def _flags_json(flags: list[RiskFlag]) -> list[dict]:
    return [f.model_dump(mode="json") for f in flags]


def persist_evaluation(session: Session, result: EvaluationResult) -> Signal:
    """Store snapshot + signal + per-agent outputs for one cycle (trade or not)."""
    ctx = result.ctx
    regime = result.regime

    snapshot = MarketSnapshot(
        symbol=ctx.symbol,
        as_of=ctx.as_of,
        last_close=ctx.last_close(Timeframe.M5) if ctx.has(Timeframe.M5) else None,
        h1_atr=result.reference_atr,
        adx=regime.adx,
        trend_regime=regime.trend_regime.value,
        phase_regime=regime.phase_regime.value,
        volatility_regime=regime.volatility_regime.value,
        prices={tf.value: float(df["close"].iloc[-1]) for tf, df in ctx.candles.items() if not df.empty},
    )
    session.add(snapshot)
    session.flush()

    d: TradingDecision = result.decision
    signal = Signal(
        snapshot_id=snapshot.id,
        symbol=d.symbol,
        decision=d.decision.value,
        bias=d.bias.value,
        confidence=d.confidence,
        quality_score=d.quality_score,
        net_score=d.net_directional_score,
        agreement=d.agreement,
        reasoning=d.reasoning,
        sizing=d.sizing.model_dump(mode="json") if d.sizing else None,
        risk_flags=_flags_json(d.risk_flags),
    )
    session.add(signal)
    session.flush()

    for output in result.outputs.values():
        session.add(
            AgentOutputRow(
                signal_id=signal.id,
                snapshot_id=snapshot.id,
                agent=output.agent.value,
                bias=output.bias.value,
                confidence=output.confidence,
                reasoning=output.reasoning,
                risk_flags=_flags_json(output.risk_flags),
                analysis=output.model_dump(mode="json", exclude={"risk_flags"}),
                model=output.model,
                latency_ms=output.latency_ms,
                error=output.error,
            )
        )
    # Risk Manager output is not in `outputs`; record it too for a complete trail.
    session.add(
        AgentOutputRow(
            signal_id=signal.id,
            snapshot_id=snapshot.id,
            agent=AgentName.RISK_MANAGER.value,
            bias=result.risk.bias.value,
            confidence=result.risk.confidence,
            reasoning=result.risk.reasoning,
            risk_flags=_flags_json(result.risk.risk_flags),
            analysis=result.risk.model_dump(mode="json", exclude={"risk_flags"}),
            model=result.risk.model,
            latency_ms=result.risk.latency_ms,
        )
    )
    return signal


def record_trade_proposed(session: Session, signal_id, sizing: PositionSizing) -> Trade:
    trade = Trade(
        signal_id=signal_id,
        symbol=sizing.symbol,
        side=sizing.side.value,
        status="proposed",
        volume=sizing.lot_size,
        entry_price=sizing.entry,
        stop_loss=sizing.stop_loss,
        take_profits=[tp.model_dump(mode="json") for tp in sizing.take_profits],
        risk_amount=sizing.risk_amount,
        risk_pct=sizing.risk_pct,
        reward_risk=sizing.reward_risk,
    )
    session.add(trade)
    session.flush()
    return trade


def mark_trade_open(session: Session, trade: Trade, *, fill_price: float, broker_order_id: int | None, slippage: float | None) -> None:
    trade.status = "open"
    trade.entry_price = fill_price
    trade.broker_order_id = broker_order_id
    trade.slippage_points = slippage
    trade.opened_at = datetime.now(UTC)


def close_trade(session: Session, trade: Trade, *, exit_price: float, pnl: float, r_multiple: float) -> None:
    trade.status = "closed"
    trade.exit_price = exit_price
    trade.pnl = pnl
    trade.r_multiple = r_multiple
    trade.closed_at = datetime.now(UTC)


def record_risk_event(session: Session, *, event_type: str, message: str, severity: str = "warning", equity: float | None = None, drawdown_pct: float | None = None, consecutive_losses: int | None = None) -> None:
    session.add(RiskEvent(event_type=event_type, message=message, severity=severity, equity=equity, drawdown_pct=drawdown_pct, consecutive_losses=consecutive_losses))


def save_performance_report(session: Session, report: PerformanceReport) -> PerformanceMetric:
    row = PerformanceMetric(
        window_start=report.window_start, window_end=report.window_end, trades=report.trades,
        win_rate=report.win_rate, profit_factor=report.profit_factor, expectancy_r=report.expectancy_r,
        sharpe=report.sharpe, sortino=report.sortino, max_drawdown_pct=report.max_drawdown_pct,
        max_drawdown_r=report.max_drawdown_r, avg_win_r=report.avg_win_r, avg_loss_r=report.avg_loss_r,
        best_conditions=report.best_conditions, worst_conditions=report.worst_conditions,
        insights=[i.model_dump(mode="json") for i in report.insights],
    )
    session.add(row)
    session.flush()
    return row


def fetch_closed_trades(session: Session, *, limit: int = 1000) -> list[ClosedTrade]:
    """Load closed trades joined to their signal/snapshot context for the Learning Engine."""
    stmt = (
        select(Trade, Signal, MarketSnapshot)
        .join(Signal, Trade.signal_id == Signal.id, isouter=True)
        .join(MarketSnapshot, Signal.snapshot_id == MarketSnapshot.id, isouter=True)
        .where(Trade.status == "closed")
        .order_by(Trade.closed_at.desc())
        .limit(limit)
    )
    out: list[ClosedTrade] = []
    for trade, signal, snap in session.execute(stmt).all():
        if trade.r_multiple is None or trade.closed_at is None:
            continue
        flag_codes = {f.get("code") for f in (signal.risk_flags or [])} if signal else set()
        out.append(
            ClosedTrade(
                id=str(trade.id),
                opened_at=trade.opened_at or trade.created_at,
                closed_at=trade.closed_at,
                side=OrderSide(trade.side),
                r_multiple=float(trade.r_multiple),
                pnl=float(trade.pnl or 0.0),
                quality_score=float(signal.quality_score) if signal else None,
                agreement=float(signal.agreement) if signal else None,
                net_score=float(signal.net_score) if signal else None,
                regime=snap.trend_regime if snap else None,
                volatility_regime=snap.volatility_regime if snap else None,
                hour=(trade.opened_at or trade.created_at).hour,
                near_news=bool(flag_codes & _NEWS_FLAG_CODES),
            )
        )
    return out
