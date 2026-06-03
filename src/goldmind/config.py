"""Centralized, validated configuration.

Design rationale
----------------
* **One source of truth.** Every tunable — risk limits, decision weights, model
  names, credentials — is declared here and validated at startup. A misconfigured
  risk limit should fail loudly on boot, never silently at 3am in production.
* **12-factor.** Values come from the environment / `.env`; secrets never live in
  code. Nested groups (`risk`, `weights`) use the ``GOLDMIND_<GROUP>__<FIELD>``
  convention; third-party secrets keep their conventional names
  (``OPENAI_API_KEY``, ``MT5_LOGIN``).
* **Immutable & cached.** ``get_settings()`` is memoized so the same validated
  object is shared process-wide.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from goldmind.core.enums import AgentName, Environment, ExecutionMode, Timeframe


class RiskConfig(BaseModel):
    """Hard risk limits. These are the system's spine — the Risk Manager and the
    daily circuit breaker enforce them. Defaults are deliberately conservative and
    prop-firm compatible (FTMO/MFF-style: small per-trade risk, tight daily DD)."""

    max_risk_per_trade: float = Field(0.005, gt=0, le=0.02, description="Fraction of equity risked per trade (0.5%).")
    max_daily_drawdown: float = Field(0.02, gt=0, le=0.10, description="Daily loss that trips the circuit breaker (2%).")
    max_total_drawdown: float = Field(0.06, gt=0, le=0.20, description="Account-level max drawdown stop (6%).")
    max_consecutive_losses: int = Field(3, ge=1, le=10)
    max_trades_per_day: int = Field(5, ge=1, le=20, description="Quality-over-quantity cap.")
    max_concurrent_positions: int = Field(1, ge=1, le=5, description="Gold is one instrument; default to a single position.")
    min_reward_risk: float = Field(1.8, ge=1.0, description="Reject setups below this reward:risk.")

    # Trade-management defaults (ATR-anchored so they adapt to volatility).
    default_atr_stop_mult: float = Field(1.5, gt=0, description="Stop distance = mult * ATR.")
    tp_r_multiples: list[float] = Field(default_factory=lambda: [1.5, 2.5, 4.0], description="Take-profit ladder in R multiples.")
    tp_partials: list[float] = Field(default_factory=lambda: [0.5, 0.3, 0.2], description="Fraction closed at each TP (sums to 1).")
    break_even_at_r: float = Field(1.0, ge=0, description="Move SL to break-even after +1R.")
    trailing_atr_mult: float = Field(2.0, gt=0, description="Trailing-stop distance in ATR once trailing engages.")

    circuit_breaker_cooldown_hours: int = Field(24, ge=1, description="Flat period after a circuit-breaker trip.")
    risk_free_rate: float = Field(0.0, description="Annualized RF rate for Sharpe/Sortino.")

    @model_validator(mode="after")
    def _check(self) -> RiskConfig:
        if self.max_daily_drawdown >= self.max_total_drawdown:
            raise ValueError("max_daily_drawdown must be < max_total_drawdown")
        if len(self.tp_r_multiples) != len(self.tp_partials):
            raise ValueError("tp_r_multiples and tp_partials must be the same length")
        if abs(sum(self.tp_partials) - 1.0) > 1e-6:
            raise ValueError("tp_partials must sum to 1.0")
        if any(self.tp_r_multiples[i] >= self.tp_r_multiples[i + 1] for i in range(len(self.tp_r_multiples) - 1)):
            raise ValueError("tp_r_multiples must be strictly increasing")
        return self


class DecisionWeights(BaseModel):
    """Weights for the Decision Engine's weighted vote (matches the brief).

    Six analytical agents cast a *directional* vote; the Risk Manager is a gate
    whose weight expresses how much execution-feasibility shapes the final
    trade-quality score. ``scoring_weights`` renormalizes the six voters to 1.0.
    """

    market_structure: float = 0.25
    technical: float = 0.20
    macro: float = 0.20
    news_sentiment: float = 0.10
    chart_vision: float = 0.10
    market_regime: float = 0.10
    risk_manager: float = 0.05

    @model_validator(mode="after")
    def _sums_to_one(self) -> DecisionWeights:
        total = (
            self.market_structure + self.technical + self.macro + self.news_sentiment
            + self.chart_vision + self.market_regime + self.risk_manager
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Decision weights must sum to 1.0 (got {total:.4f})")
        return self

    def scoring_weights(self) -> dict[AgentName, float]:
        """Directional-voter weights, renormalized to sum to 1.0 (excludes risk)."""
        raw = {
            AgentName.MARKET_STRUCTURE: self.market_structure,
            AgentName.TECHNICAL: self.technical,
            AgentName.MACRO: self.macro,
            AgentName.NEWS_SENTIMENT: self.news_sentiment,
            AgentName.CHART_VISION: self.chart_vision,
            AgentName.MARKET_REGIME: self.market_regime,
        }
        s = sum(raw.values())
        return {k: v / s for k, v in raw.items()}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="GOLDMIND_",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Runtime ----
    environment: Environment = Environment.DEV
    execution_mode: ExecutionMode = ExecutionMode.SHADOW
    log_level: str = "INFO"
    symbol: str = "XAUUSD"
    timeframes: list[Timeframe] = Field(default_factory=lambda: [Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4])

    # ---- LLM models / providers ----
    reasoning_model: str = "claude-sonnet-4-6"
    vision_model: str = "gpt-4o"
    fast_model: str = "claude-haiku-4-5-20251001"
    llm_temperature: float = 0.1
    llm_timeout_s: int = 60
    openai_api_key: str | None = Field(default=None, validation_alias=AliasChoices("OPENAI_API_KEY"))
    anthropic_api_key: str | None = Field(default=None, validation_alias=AliasChoices("ANTHROPIC_API_KEY"))

    # ---- Database ----
    database_url: str = "postgresql+psycopg://goldmind:goldmind@localhost:5432/goldmind"

    # ---- MetaTrader 5 (execution node) ----
    mt5_login: int | None = Field(default=None, validation_alias=AliasChoices("MT5_LOGIN"))
    mt5_password: str | None = Field(default=None, validation_alias=AliasChoices("MT5_PASSWORD"))
    mt5_server: str | None = Field(default=None, validation_alias=AliasChoices("MT5_SERVER"))
    mt5_terminal_path: str | None = Field(default=None, validation_alias=AliasChoices("MT5_TERMINAL_PATH"))
    mt5_symbol: str = Field(default="XAUUSD", validation_alias=AliasChoices("MT5_SYMBOL"))

    # ---- Data feeds ----
    fred_api_key: str | None = Field(default=None, validation_alias=AliasChoices("FRED_API_KEY"))
    newsapi_key: str | None = Field(default=None, validation_alias=AliasChoices("NEWSAPI_KEY"))
    alphavantage_key: str | None = Field(default=None, validation_alias=AliasChoices("ALPHAVANTAGE_KEY"))
    forexfactory_calendar_url: str = Field(
        default="https://nfs.faireconomy.media/ff_calendar_thisweek.json",
        validation_alias=AliasChoices("FOREXFACTORY_CALENDAR_URL"),
    )

    # ---- Observability ----
    prometheus_port: int = Field(default=9000, validation_alias=AliasChoices("PROMETHEUS_PORT"))

    # ---- Nested groups ----
    risk: RiskConfig = Field(default_factory=RiskConfig)
    weights: DecisionWeights = Field(default_factory=DecisionWeights)

    @property
    def is_live(self) -> bool:
        return self.execution_mode is ExecutionMode.FULL_AUTO and self.environment is Environment.PROD


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide, validated settings singleton."""
    return Settings()
