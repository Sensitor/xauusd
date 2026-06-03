"""Agent 2 — Technical Analyst.

Computes RSI, MACD, EMA(20/50/200), ATR, Bollinger Bands, relative volume and a
volatility read across timeframes, then distills them into the three scores the
brief asks for:
  * bullish_bearish_score  in [-1, 1]
  * indicator_alignment_score in [0, 1]  (how much the indicators agree)
  * momentum_score in [-1, 1]

Every sub-indicator casts an explicit vote, so the output is fully explainable
(the dashboard can show exactly which indicators agreed and which dissented).
"""

from __future__ import annotations

from goldmind.agents.base import BaseAgent
from goldmind.core.context import MarketContext
from goldmind.core.enums import AgentName, Bias, Severity, Timeframe
from goldmind.core.schemas import AgentOutput, IndicatorSnapshot, TechnicalOutput
from goldmind.indicators.technical import compute_snapshot

# Trend-following weighting: lean on the higher timeframes.
_TF_WEIGHTS: dict[Timeframe, float] = {
    Timeframe.M5: 0.15,
    Timeframe.M15: 0.25,
    Timeframe.H1: 0.30,
    Timeframe.H4: 0.30,
}


def _indicator_votes(s: IndicatorSnapshot) -> dict[str, int]:
    """Each indicator votes -1 / 0 / +1. Missing inputs simply don't vote."""
    votes: dict[str, int] = {}
    if s.close is not None and s.ema20 is not None:
        votes["price_vs_ema20"] = 1 if s.close > s.ema20 else -1
    if s.ema20 is not None and s.ema50 is not None:
        votes["ema20_vs_ema50"] = 1 if s.ema20 > s.ema50 else -1
    if s.ema50 is not None and s.ema200 is not None:
        votes["ema50_vs_ema200"] = 1 if s.ema50 > s.ema200 else -1
    if s.rsi is not None:
        votes["rsi"] = 1 if s.rsi > 55 else (-1 if s.rsi < 45 else 0)
    if s.macd_hist is not None:
        votes["macd"] = 1 if s.macd_hist > 0 else (-1 if s.macd_hist < 0 else 0)
    if s.close is not None and s.bb_mid is not None:
        votes["bollinger"] = 1 if s.close > s.bb_mid else -1
    return votes


def _tf_score(votes: dict[str, int]) -> float:
    active = [v for v in votes.values() if v != 0]
    return sum(active) / len(active) if active else 0.0


def _momentum(s: IndicatorSnapshot) -> float:
    m = 0.0
    if s.macd_hist is not None and s.atr:
        m += max(-1.0, min(1.0, s.macd_hist / s.atr))  # histogram scaled by volatility
    if s.rsi is not None:
        m += (s.rsi - 50.0) / 50.0
    return max(-1.0, min(1.0, m / 2.0))


class TechnicalAgent(BaseAgent):
    name = AgentName.TECHNICAL
    output_cls = TechnicalOutput

    def analyze(self, ctx: MarketContext) -> AgentOutput:
        snapshots: list[IndicatorSnapshot] = []
        weighted_dir = 0.0
        weight_total = 0.0
        momentum_acc = 0.0
        agree = 0
        total_votes = 0
        net_sign_accumulator = 0.0

        per_tf: list[tuple[Timeframe, float, dict[str, int]]] = []
        for tf in (Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4):
            if not ctx.has(tf):
                continue
            df = ctx.frame(tf)
            if len(df) < 60:  # need warm-up for EMA200-ish context
                continue
            s = compute_snapshot(df, tf)
            snapshots.append(s)
            votes = _indicator_votes(s)
            score = _tf_score(votes)
            per_tf.append((tf, score, votes))
            w = _TF_WEIGHTS[tf]
            weighted_dir += w * score
            weight_total += w
            momentum_acc += w * _momentum(s)
            net_sign_accumulator += w * score

        if not snapshots:
            return self._degraded("insufficient candles for indicators", code="data_unavailable")

        bullish_bearish = weighted_dir / weight_total if weight_total else 0.0
        momentum = momentum_acc / weight_total if weight_total else 0.0
        net_sign = 1 if bullish_bearish >= 0 else -1

        # Alignment: of every cast vote, how many point with the net direction.
        for _tf, _score, votes in per_tf:
            for v in votes.values():
                if v != 0:
                    total_votes += 1
                    if (v > 0) == (net_sign > 0):
                        agree += 1
        alignment = agree / total_votes if total_votes else 0.0

        bias = Bias.BULLISH if bullish_bearish > 0.2 else (Bias.BEARISH if bullish_bearish < -0.2 else Bias.NEUTRAL)
        # Confidence blends conviction (|score|) with cross-indicator agreement.
        confidence = round(min(1.0, abs(bullish_bearish)) * (0.4 + 0.6 * alignment), 3)

        out = TechnicalOutput(
            agent=self.name,
            bias=bias,
            confidence=confidence,
            bullish_bearish_score=round(bullish_bearish, 3),
            indicator_alignment_score=round(alignment, 3),
            momentum_score=round(momentum, 3),
            snapshots=snapshots,
            reasoning=self._explain(bias, bullish_bearish, alignment, momentum, per_tf),
        )

        # Volatility context as a flag (regime agent owns the formal call).
        h1 = next((s for s in snapshots if s.timeframe is Timeframe.H1), snapshots[-1])
        if h1.atr_pct is not None and h1.atr_pct > 0.012:
            out.add_flag("elevated_volatility", f"H1 ATR is {h1.atr_pct:.2%} of price — widen stops / reduce size.", Severity.WARNING)
        if abs(bullish_bearish) < 0.15:
            out.add_flag("no_technical_edge", "Indicators are mixed/flat — no clear technical edge.", Severity.INFO)
        return out

    @staticmethod
    def _explain(bias: Bias, score: float, alignment: float, momentum: float, per_tf) -> str:
        head = f"Technical bias {bias.value} (score {score:+.2f}, alignment {alignment:.0%}, momentum {momentum:+.2f})."
        details = [f"{tf.value}:{sc:+.2f}" for tf, sc, _votes in per_tf]
        return head + " Per-TF: " + ", ".join(details) + "."
