"""SQLAlchemy 2.0 ORM models — the typed mirror of ``schema.sql``.

Generic column types (``JSON.with_variant(JSONB)``, ``Uuid``) keep the models
importable and unit-testable against SQLite while using native JSONB/UUID on
PostgreSQL in production.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

# JSONB on PostgreSQL, plain JSON elsewhere (tests on SQLite).
JSON_T = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[uuid.UUID] = _uuid_pk()
    symbol: Mapped[str] = mapped_column(String, default="XAUUSD")
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_close: Mapped[float | None] = mapped_column(Numeric(14, 4))
    h1_atr: Mapped[float | None] = mapped_column(Numeric(14, 4))
    adx: Mapped[float | None] = mapped_column(Numeric(8, 3))
    trend_regime: Mapped[str | None] = mapped_column(String)
    phase_regime: Mapped[str | None] = mapped_column(String)
    volatility_regime: Mapped[str | None] = mapped_column(String)
    prices: Mapped[dict] = mapped_column(JSON_T, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (CheckConstraint("decision IN ('BUY','SELL','NO_TRADE')", name="ck_signal_decision"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("market_snapshots.id", ondelete="SET NULL"))
    symbol: Mapped[str] = mapped_column(String, default="XAUUSD")
    decision: Mapped[str] = mapped_column(String)
    bias: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4))
    quality_score: Mapped[float] = mapped_column(Numeric(6, 2))
    net_score: Mapped[float] = mapped_column(Numeric(6, 4))
    agreement: Mapped[float] = mapped_column(Numeric(5, 4))
    reasoning: Mapped[str | None] = mapped_column(Text)
    sizing: Mapped[dict | None] = mapped_column(JSON_T)
    risk_flags: Mapped[list] = mapped_column(JSON_T, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    agent_outputs: Mapped[list[AgentOutputRow]] = relationship(back_populates="signal", cascade="all, delete-orphan")


class AgentOutputRow(Base):
    __tablename__ = "agent_outputs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    signal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"))
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("market_snapshots.id", ondelete="SET NULL"))
    agent: Mapped[str] = mapped_column(String)
    bias: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4))
    reasoning: Mapped[str | None] = mapped_column(Text)
    risk_flags: Mapped[list] = mapped_column(JSON_T, default=list)
    analysis: Mapped[dict] = mapped_column(JSON_T, default=dict)
    model: Mapped[str | None] = mapped_column(String)
    latency_ms: Mapped[float | None] = mapped_column(Numeric(10, 2))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    signal: Mapped[Signal] = relationship(back_populates="agent_outputs")


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (CheckConstraint("side IN ('buy','sell')", name="ck_trade_side"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    signal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("signals.id", ondelete="SET NULL"))
    symbol: Mapped[str] = mapped_column(String, default="XAUUSD")
    side: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="proposed")
    volume: Mapped[float] = mapped_column(Numeric(10, 2))
    entry_price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    stop_loss: Mapped[float | None] = mapped_column(Numeric(14, 4))
    take_profits: Mapped[list] = mapped_column(JSON_T, default=list)
    exit_price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    broker_order_id: Mapped[int | None] = mapped_column(BigInteger)
    risk_amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    risk_pct: Mapped[float | None] = mapped_column(Numeric(7, 5))
    reward_risk: Mapped[float | None] = mapped_column(Numeric(7, 2))
    pnl: Mapped[float | None] = mapped_column(Numeric(14, 2))
    r_multiple: Mapped[float | None] = mapped_column(Numeric(8, 3))
    mae_r: Mapped[float | None] = mapped_column(Numeric(8, 3))
    mfe_r: Mapped[float | None] = mapped_column(Numeric(8, 3))
    slippage_points: Mapped[float | None] = mapped_column(Numeric(10, 2))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Screenshot(Base):
    __tablename__ = "screenshots"

    id: Mapped[uuid.UUID] = _uuid_pk()
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("market_snapshots.id", ondelete="SET NULL"))
    symbol: Mapped[str] = mapped_column(String, default="XAUUSD")
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str | None] = mapped_column(String)
    uri: Mapped[str] = mapped_column(Text)
    vision_output: Mapped[dict | None] = mapped_column(JSON_T)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NewsEventRow(Base):
    __tablename__ = "news_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    title: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String)
    importance: Mapped[str] = mapped_column(String, default="info")
    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sentiment: Mapped[float | None] = mapped_column(Numeric(5, 4))
    url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PerformanceMetric(Base):
    __tablename__ = "performance_metrics"

    id: Mapped[uuid.UUID] = _uuid_pk()
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trades: Mapped[int] = mapped_column(Integer)
    win_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))
    profit_factor: Mapped[float | None] = mapped_column(Numeric(8, 3))
    expectancy_r: Mapped[float | None] = mapped_column(Numeric(8, 4))
    sharpe: Mapped[float | None] = mapped_column(Numeric(8, 3))
    sortino: Mapped[float | None] = mapped_column(Numeric(8, 3))
    max_drawdown_pct: Mapped[float | None] = mapped_column(Numeric(7, 4))
    max_drawdown_r: Mapped[float | None] = mapped_column(Numeric(8, 3))
    avg_win_r: Mapped[float | None] = mapped_column(Numeric(8, 3))
    avg_loss_r: Mapped[float | None] = mapped_column(Numeric(8, 3))
    best_conditions: Mapped[dict] = mapped_column(JSON_T, default=dict)
    worst_conditions: Mapped[dict] = mapped_column(JSON_T, default=dict)
    insights: Mapped[list] = mapped_column(JSON_T, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    event_type: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String, default="warning")
    message: Mapped[str] = mapped_column(Text)
    equity: Mapped[float | None] = mapped_column(Numeric(14, 2))
    drawdown_pct: Mapped[float | None] = mapped_column(Numeric(7, 4))
    consecutive_losses: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
