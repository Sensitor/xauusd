"""Structured I/O contracts for every agent and engine.

Why Pydantic everywhere
-----------------------
The brief requires that *every* agent emit ``analysis``, a ``confidence`` score,
``reasoning``, and ``risk flags`` — and that every decision be explainable and
logged. Typed models give us: (1) validation at the boundary (an LLM that returns
a confidence of 1.7 is rejected, not trusted); (2) a single serialization format
shared by the LangGraph state, the PostgreSQL layer, the API, and the dashboard;
(3) self-documenting structures the Learning Engine can mine later.

Heavy numeric inputs (OHLCV frames) intentionally live in
``goldmind.core.context.MarketContext`` (a dataclass over pandas), not here, to
keep these contracts JSON-clean.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from goldmind.core.enums import (
    AgentName,
    Bias,
    OrderSide,
    OrderType,
    PhaseRegime,
    RiskEnvironment,
    Severity,
    Timeframe,
    TradeDecision,
    TrendRegime,
    VolatilityRegime,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


# =====================================================================
# Primitives
# =====================================================================
class RiskFlag(BaseModel):
    """A structured warning emitted by any agent. The Decision Engine and Risk
    Manager treat CRITICAL flags as hard vetoes regardless of vote scores."""

    code: str = Field(..., description="Machine code, e.g. 'high_impact_news_window'.")
    message: str
    severity: Severity = Severity.WARNING
    source: AgentName | None = None


class AgentOutput(BaseModel):
    """Base output every analytical agent returns. Specialized agents subclass
    this and add a typed ``analysis`` payload via their own fields."""

    model_config = ConfigDict(use_enum_values=False)

    agent: AgentName
    bias: Bias = Bias.NEUTRAL
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Calibrated self-confidence in [0,1].")
    reasoning: str = Field("", description="Human-readable explanation of the conclusion.")
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    analysis: dict[str, Any] = Field(default_factory=dict, description="Structured, agent-specific detail.")

    # provenance / observability
    model: str | None = None
    latency_ms: float | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    error: str | None = Field(default=None, description="Set if the agent degraded; consumers should treat as low-information.")

    @property
    def signed_confidence(self) -> float:
        """confidence * direction, in [-1, 1]. The atom of the weighted vote."""
        return self.confidence * self.bias.sign

    def add_flag(self, code: str, message: str, severity: Severity = Severity.WARNING) -> None:
        self.risk_flags.append(RiskFlag(code=code, message=message, severity=severity, source=self.agent))


# =====================================================================
# Agent 1 — Market Structure (SMC)
# =====================================================================
class TimeframeTrend(BaseModel):
    timeframe: Timeframe
    trend: Bias
    last_swing_high: float | None = None
    last_swing_low: float | None = None
    bos: bool = Field(False, description="Break of structure on this timeframe.")
    choch: bool = Field(False, description="Change of character on this timeframe.")


class FairValueGap(BaseModel):
    timeframe: Timeframe
    direction: Bias            # bullish (demand) or bearish (supply) imbalance
    top: float
    bottom: float
    mitigated: bool = False


class OrderBlock(BaseModel):
    timeframe: Timeframe
    direction: Bias
    top: float
    bottom: float


class LiquidityPool(BaseModel):
    price: float
    kind: str = Field(..., description="'buyside' (above highs) or 'sellside' (below lows).")
    swept: bool = False


class MarketStructureOutput(AgentOutput):
    agent: AgentName = AgentName.MARKET_STRUCTURE
    structural_bias: Bias = Bias.NEUTRAL
    timeframe_trends: list[TimeframeTrend] = Field(default_factory=list)
    fair_value_gaps: list[FairValueGap] = Field(default_factory=list)
    order_blocks: list[OrderBlock] = Field(default_factory=list)
    liquidity_pools: list[LiquidityPool] = Field(default_factory=list)
    premium_discount: float | None = Field(None, ge=0, le=1, description="0=deep discount, 1=deep premium of dealing range.")
    mtf_alignment: float = Field(0.0, ge=-1, le=1, description="Weighted agreement across M5/M15/H1/H4.")


# =====================================================================
# Agent 2 — Technical
# =====================================================================
class IndicatorSnapshot(BaseModel):
    timeframe: Timeframe
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    ema20: float | None = None
    ema50: float | None = None
    ema200: float | None = None
    atr: float | None = None
    atr_pct: float | None = None
    bb_upper: float | None = None
    bb_mid: float | None = None
    bb_lower: float | None = None
    bb_width: float | None = None
    rel_volume: float | None = Field(None, description="Volume vs. its rolling average.")
    close: float | None = None


class TechnicalOutput(AgentOutput):
    agent: AgentName = AgentName.TECHNICAL
    bullish_bearish_score: float = Field(0.0, ge=-1, le=1)
    indicator_alignment_score: float = Field(0.0, ge=0, le=1)
    momentum_score: float = Field(0.0, ge=-1, le=1)
    snapshots: list[IndicatorSnapshot] = Field(default_factory=list)


# =====================================================================
# Agent 3 — Macro
# =====================================================================
class MacroIndicator(BaseModel):
    name: str                       # e.g. "CPI YoY", "DXY", "US10Y"
    value: float | None = None
    prior: float | None = None
    surprise: float | None = Field(None, description="actual - consensus (sign matters).")
    gold_impact: Bias = Bias.NEUTRAL


class MacroOutput(AgentOutput):
    agent: AgentName = AgentName.MACRO
    macro_bias: Bias = Bias.NEUTRAL
    risk_environment: RiskEnvironment = RiskEnvironment.NEUTRAL
    dxy_trend: Bias = Bias.NEUTRAL
    yields_trend: Bias = Bias.NEUTRAL
    indicators: list[MacroIndicator] = Field(default_factory=list)


# =====================================================================
# Agent 4 — News & Sentiment
# =====================================================================
class NewsEvent(BaseModel):
    title: str
    source: str
    published_at: datetime | None = None
    scheduled_at: datetime | None = None
    importance: Severity = Severity.INFO     # INFO/WARNING/CRITICAL ~ low/med/high impact
    sentiment: float = Field(0.0, ge=-1, le=1)
    is_scheduled: bool = False
    url: str | None = None


class NewsSentimentOutput(AgentOutput):
    agent: AgentName = AgentName.NEWS_SENTIMENT
    sentiment_score: float = Field(0.0, ge=-1, le=1)
    risk_level: Severity = Severity.INFO
    minutes_to_next_high_impact: float | None = None
    in_blackout_window: bool = Field(False, description="True if inside the no-trade window around a high-impact event.")
    events: list[NewsEvent] = Field(default_factory=list)


# =====================================================================
# Agent 5 — Chart Vision
# =====================================================================
class ChartPattern(BaseModel):
    name: str                        # "double_top", "head_and_shoulders", ...
    direction: Bias
    confidence: float = Field(0.0, ge=0, le=1)


class ChartVisionOutput(AgentOutput):
    agent: AgentName = AgentName.CHART_VISION
    detected_trend: Bias = Bias.NEUTRAL
    patterns: list[ChartPattern] = Field(default_factory=list)
    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)
    risk_areas: list[str] = Field(default_factory=list)
    image_ref: str | None = None


# =====================================================================
# Agent 6 — Market Regime
# =====================================================================
class MarketRegimeOutput(AgentOutput):
    agent: AgentName = AgentName.MARKET_REGIME
    trend_regime: TrendRegime = TrendRegime.RANGING
    phase_regime: PhaseRegime = PhaseRegime.COMPRESSION
    volatility_regime: VolatilityRegime = VolatilityRegime.NORMAL
    adx: float | None = None
    recommended_behavior: str = ""
    # Multiplier the Decision Engine applies to required quality in this regime.
    quality_multiplier: float = Field(1.0, gt=0, description=">1 demands higher conviction (e.g. chop), <1 is permissive.")


# =====================================================================
# Account state & Risk Manager (Agent 7)
# =====================================================================
class AccountState(BaseModel):
    """Snapshot the Risk Manager needs to size and to enforce drawdown rules."""

    equity: float
    balance: float
    currency: str = "USD"
    peak_equity: float
    open_positions: int = 0
    daily_realized_pnl: float = 0.0
    consecutive_losses: int = 0
    trades_today: int = 0

    @property
    def drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.equity) / self.peak_equity)

    @property
    def daily_pnl_pct(self) -> float:
        denom = self.equity - self.daily_realized_pnl
        return self.daily_realized_pnl / denom if denom else 0.0


class TakeProfit(BaseModel):
    price: float
    r_multiple: float
    close_fraction: float = Field(..., gt=0, le=1)


class PositionSizing(BaseModel):
    symbol: str
    side: OrderSide
    entry: float
    stop_loss: float
    take_profits: list[TakeProfit] = Field(default_factory=list)
    lot_size: float = Field(..., ge=0)
    risk_amount: float = Field(..., ge=0, description="Cash at risk to the stop.")
    risk_pct: float = Field(..., ge=0)
    reward_risk: float = Field(..., ge=0, description="Blended RR across the TP ladder.")
    stop_distance: float = Field(..., ge=0, description="|entry - stop| in price.")
    break_even_price: float | None = None
    trailing_distance: float | None = None


class RiskAssessment(AgentOutput):
    agent: AgentName = AgentName.RISK_MANAGER
    approved: bool = False
    rejection_reason: str | None = None
    sizing: PositionSizing | None = None
    account: AccountState | None = None
    circuit_breaker_active: bool = False


# =====================================================================
# Agent 8 — Decision Engine
# =====================================================================
class AgentVote(BaseModel):
    agent: AgentName
    bias: Bias
    confidence: float
    weight: float
    contribution: float = Field(..., description="weight * signed_confidence; the agent's push on the net score.")


class TradingDecision(BaseModel):
    """The system's terminal, explainable verdict for one evaluation cycle."""

    id: UUID = Field(default_factory=uuid4)
    symbol: str
    decision: TradeDecision
    bias: Bias
    confidence: float = Field(..., ge=0, le=1)
    quality_score: float = Field(..., ge=0, le=100, description="0–100 setup quality (gates trade entry).")
    net_directional_score: float = Field(..., ge=-1, le=1)
    agreement: float = Field(..., ge=0, le=1, description="How aligned the voters are (1 = unanimous).")
    votes: list[AgentVote] = Field(default_factory=list)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    reasoning: str = ""
    sizing: PositionSizing | None = None
    snapshot_id: UUID | None = None
    created_at: datetime = Field(default_factory=_utcnow)


# =====================================================================
# Agent 9 — Execution
# =====================================================================
class OrderRequest(BaseModel):
    symbol: str
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    volume: float = Field(..., gt=0)
    price: float | None = None            # required for limit/stop
    stop_loss: float | None = None
    take_profit: float | None = None
    deviation_points: int = 20            # max slippage tolerated
    comment: str = "goldmind"
    decision_id: UUID | None = None


class OrderResult(BaseModel):
    accepted: bool
    broker_order_id: int | None = None
    filled_price: float | None = None
    requested_price: float | None = None
    slippage_points: float | None = None
    latency_ms: float | None = None
    retcode: int | None = None
    message: str = ""


class OpenPosition(BaseModel):
    ticket: int
    symbol: str
    side: OrderSide
    volume: float
    entry: float
    stop_loss: float | None = None
    take_profit: float | None = None
    unrealized_pnl: float = 0.0
    opened_at: datetime | None = None


# =====================================================================
# Agent 10 — Learning Engine
# =====================================================================
class LearningInsight(BaseModel):
    category: str = Field(..., description="'filter' | 'risk' | 'selection' | 'regime'.")
    statement: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(0.0, ge=0, le=1)


class PerformanceReport(BaseModel):
    window_start: datetime
    window_end: datetime
    trades: int
    win_rate: float
    profit_factor: float | None = Field(None, description="None when there are no losing trades (undefined / ∞).")
    expectancy_r: float = Field(..., description="Average R per trade.")
    sharpe: float | None = None
    sortino: float | None = None
    max_drawdown_pct: float | None = None
    max_drawdown_r: float | None = Field(None, description="Worst peak-to-trough drawdown in R units.")
    avg_win_r: float | None = None
    avg_loss_r: float | None = None
    best_conditions: dict[str, Any] = Field(default_factory=dict)
    worst_conditions: dict[str, Any] = Field(default_factory=dict)
    insights: list[LearningInsight] = Field(default_factory=list)


# Convenience union used by the orchestrator/state.
AnyAgentOutput = (
    MarketStructureOutput
    | TechnicalOutput
    | MacroOutput
    | NewsSentimentOutput
    | ChartVisionOutput
    | MarketRegimeOutput
    | RiskAssessment
    | AgentOutput
)

__all__ = [name for name in dir() if name[0].isupper()] + ["AnyAgentOutput"]
