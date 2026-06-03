"""Enumerations used across the whole system.

Keeping these centralized guarantees that every agent, the database layer, the
API, and the backtester speak the *same* vocabulary. String-valued enums make
them JSON/DB friendly and human-readable in logs and dashboards.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """str-backed enum (Py3.11 has enum.StrEnum, but we keep an explicit base
    so `value` round-trips cleanly through Pydantic v2 and JSON)."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class Environment(StrEnum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class ExecutionMode(StrEnum):
    """How far the system is allowed to act on its own conclusions."""

    SHADOW = "shadow"          # analyze + log only; never place orders
    SEMI_AUTO = "semi_auto"    # propose; a human approves before execution
    FULL_AUTO = "full_auto"    # execute approved decisions automatically


class Timeframe(StrEnum):
    M5 = "M5"
    M15 = "M15"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"

    @property
    def minutes(self) -> int:
        return {"M5": 5, "M15": 15, "H1": 60, "H4": 240, "D1": 1440}[self.value]

    @classmethod
    def ordered(cls) -> list[Timeframe]:
        """Lowest to highest timeframe — used for multi-timeframe alignment."""
        return [cls.M5, cls.M15, cls.H1, cls.H4, cls.D1]


class Bias(StrEnum):
    """Directional opinion produced by an analytical agent."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"

    @property
    def sign(self) -> int:
        return {"bullish": 1, "bearish": -1, "neutral": 0}[self.value]


class TradeDecision(StrEnum):
    """Terminal output of the Decision Engine."""

    BUY = "BUY"
    SELL = "SELL"
    NO_TRADE = "NO_TRADE"


class TrendRegime(StrEnum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"


class PhaseRegime(StrEnum):
    """Volatility-cycle phase (Bollinger/ATR based)."""

    EXPANSION = "expansion"      # volatility breaking out, ranges widening
    COMPRESSION = "compression"  # volatility contracting, coiling


class VolatilityRegime(StrEnum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class RiskEnvironment(StrEnum):
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    NEUTRAL = "neutral"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        return 1 if self is OrderSide.BUY else -1


class TradeStatus(StrEnum):
    PROPOSED = "proposed"        # decision made, awaiting approval/routing
    PENDING = "pending"          # order sent to broker, not yet filled
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AgentName(StrEnum):
    """Stable identifiers used as dict keys, DB values, and dashboard labels."""

    MARKET_STRUCTURE = "market_structure"
    TECHNICAL = "technical"
    MACRO = "macro"
    NEWS_SENTIMENT = "news_sentiment"
    CHART_VISION = "chart_vision"
    MARKET_REGIME = "market_regime"
    RISK_MANAGER = "risk_manager"
    DECISION_ENGINE = "decision_engine"
    EXECUTION = "execution"
    LEARNING = "learning"


# Agents that contribute a directional/quality opinion to the weighted vote.
# Risk Manager and the engines are *gates/aggregators*, not voters.
SCORING_AGENTS: tuple[AgentName, ...] = (
    AgentName.MARKET_STRUCTURE,
    AgentName.TECHNICAL,
    AgentName.MACRO,
    AgentName.NEWS_SENTIMENT,
    AgentName.CHART_VISION,
    AgentName.MARKET_REGIME,
)
