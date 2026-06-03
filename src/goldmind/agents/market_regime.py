"""Agent 6 — Market Regime Agent.

Classifies the environment so the rest of the system can *adapt* rather than apply
one playbook everywhere:
  * trend regime   — trending_up / trending_down / ranging   (ADX + EMA slope)
  * phase regime   — expansion / compression                  (Bollinger width vs. its history)
  * volatility     — high / normal / low                      (ATR% percentile)

The key output is ``quality_multiplier``: a scalar the Decision Engine multiplies
into the required setup quality. In chop/compression we demand *more* conviction
(multiplier > 1); in a clean trend we relax slightly (< 1). This is how the system
"avoids trading during uncertainty" mechanically.
"""

from __future__ import annotations

import numpy as np

from goldmind.agents.base import BaseAgent
from goldmind.core.context import MarketContext
from goldmind.core.enums import (
    AgentName,
    Bias,
    PhaseRegime,
    Severity,
    Timeframe,
    TrendRegime,
    VolatilityRegime,
)
from goldmind.core.schemas import AgentOutput, MarketRegimeOutput
from goldmind.indicators.technical import adx, atr, bollinger, ema


def _percentile_rank(series, value) -> float:
    arr = np.asarray(series.dropna().values, dtype=float)
    if arr.size < 20 or value is None or np.isnan(value):
        return 0.5
    return float((arr < value).mean())


class MarketRegimeAgent(BaseAgent):
    name = AgentName.MARKET_REGIME
    output_cls = MarketRegimeOutput

    #: Timeframe on which the regime is primarily judged.
    primary_tf = Timeframe.H1

    def analyze(self, ctx: MarketContext) -> AgentOutput:
        tf = self.primary_tf if ctx.has(self.primary_tf) else Timeframe.M15
        df = ctx.frame(tf)
        if len(df) < 60:
            return self._degraded("insufficient candles for regime", code="data_unavailable")

        high, low, close = df["high"], df["low"], df["close"]
        adx_series, _pdi, _mdi = adx(high, low, close)
        adx_last = float(adx_series.iloc[-1]) if not np.isnan(adx_series.iloc[-1]) else 0.0

        e50, e200 = ema(close, 50), ema(close, 200)
        slope = float(e50.iloc[-1] - e50.iloc[-5]) if len(e50) > 5 else 0.0
        e50_last, e200_last = float(e50.iloc[-1]), float(e200.iloc[-1])
        if np.isnan(e200_last):
            # Not enough history for the slow EMA: judge direction from the EMA50
            # slope and price location rather than silently defaulting to "down".
            up = slope > 0 and float(close.iloc[-1]) >= e50_last
        else:
            up = e50_last > e200_last and slope > 0

        # --- trend regime ---
        if adx_last >= 25:
            trend = TrendRegime.TRENDING_UP if up else TrendRegime.TRENDING_DOWN
        else:
            trend = TrendRegime.RANGING

        # --- volatility regime (ATR% percentile over recent history) ---
        atr_series = atr(high, low, close)
        atr_pct_series = (atr_series / close).dropna()
        atr_pct_now = float(atr_pct_series.iloc[-1]) if len(atr_pct_series) else None
        vol_rank = _percentile_rank(atr_pct_series.tail(250), atr_pct_now)
        if vol_rank >= 0.70:
            vol = VolatilityRegime.HIGH
        elif vol_rank <= 0.30:
            vol = VolatilityRegime.LOW
        else:
            vol = VolatilityRegime.NORMAL

        # --- phase regime (Bollinger width vs. its own median) ---
        _u, _m, _l, width = bollinger(close)
        width = width.dropna()
        phase = PhaseRegime.COMPRESSION
        if len(width) > 30:
            now = float(width.iloc[-1])
            med = float(width.tail(120).median())
            rising = now > float(width.iloc[-5])
            phase = PhaseRegime.EXPANSION if (now > med and rising) else PhaseRegime.COMPRESSION

        bias = {
            TrendRegime.TRENDING_UP: Bias.BULLISH,
            TrendRegime.TRENDING_DOWN: Bias.BEARISH,
            TrendRegime.RANGING: Bias.NEUTRAL,
        }[trend]

        quality_multiplier, behavior = self._policy(trend, phase, vol)
        # Confidence: strong, decisive trends are higher-confidence regime calls.
        confidence = round(min(1.0, max(0.2, (adx_last - 10) / 40)) if trend is not TrendRegime.RANGING else 0.45, 3)

        out = MarketRegimeOutput(
            agent=self.name,
            bias=bias,
            confidence=confidence,
            trend_regime=trend,
            phase_regime=phase,
            volatility_regime=vol,
            adx=round(adx_last, 2),
            quality_multiplier=round(quality_multiplier, 3),
            recommended_behavior=behavior,
            reasoning=(
                f"{tf.value} regime: {trend.value}, {phase.value}, {vol.value} volatility "
                f"(ADX {adx_last:.1f}, ATR% rank {vol_rank:.0%}). {behavior}"
            ),
            analysis={"atr_pct": atr_pct_now, "vol_percentile": round(vol_rank, 3), "ema_slope": round(slope, 4)},
        )

        if vol is VolatilityRegime.HIGH:
            out.add_flag("high_volatility_regime", "High-volatility regime — size down and widen stops.", Severity.WARNING)
        if trend is TrendRegime.RANGING and phase is PhaseRegime.COMPRESSION:
            out.add_flag("chop_regime", "Ranging + compression — low expectancy; prefer NO TRADE unless conviction is high.", Severity.WARNING)
        return out

    @staticmethod
    def _policy(trend: TrendRegime, phase: PhaseRegime, vol: VolatilityRegime) -> tuple[float, str]:
        """Map regime -> (quality multiplier, human-readable behavior)."""
        mult = 1.0
        notes: list[str] = []
        if trend is TrendRegime.RANGING:
            mult *= 1.25
            notes.append("Range: favor mean-reversion at extremes or stand aside; avoid breakout chasing.")
        else:
            mult *= 0.95
            notes.append("Trend: favor pullback continuation in the trend direction.")
        if phase is PhaseRegime.COMPRESSION:
            mult *= 1.10
            notes.append("Compression: expect a volatility expansion; wait for confirmation, don't predict the break.")
        else:
            notes.append("Expansion: momentum entries valid but chase risk is higher.")
        if vol is VolatilityRegime.HIGH:
            mult *= 1.10
            notes.append("High vol: reduce position size.")
        elif vol is VolatilityRegime.LOW:
            notes.append("Low vol: targets may be modest; mind spread/cost.")
        return mult, " ".join(notes)
