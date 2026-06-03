"""Agent 1 — Market Structure Analyst (Smart-Money-Concepts).

Detects, per timeframe and strictly causally (no repainting):
  * swing structure -> trend (HH/HL vs. LH/LL)
  * Break of Structure (BOS) and Change of Character (CHOCH)
  * Fair Value Gaps (3-candle imbalances)
  * Order Blocks (last opposite candle before an impulsive break)
  * Liquidity pools (buyside/sellside) and whether they were swept
  * Premium/Discount location within the dealing range
  * Multi-timeframe alignment across M5/M15/H1/H4

This agent is deterministic — it earns the largest decision weight precisely
because its output is reproducible and auditable, not a black-box LLM guess.
"""

from __future__ import annotations

import pandas as pd

from goldmind.agents.base import BaseAgent
from goldmind.core.context import MarketContext
from goldmind.core.enums import AgentName, Bias, Severity, Timeframe
from goldmind.core.schemas import (
    AgentOutput,
    FairValueGap,
    LiquidityPool,
    MarketStructureOutput,
    OrderBlock,
    TimeframeTrend,
)
from goldmind.indicators.technical import swing_points

# Higher timeframes carry more structural weight in the alignment score.
_TF_WEIGHTS: dict[Timeframe, float] = {
    Timeframe.M5: 0.10,
    Timeframe.M15: 0.20,
    Timeframe.H1: 0.30,
    Timeframe.H4: 0.40,
}


def _analyze_timeframe(df: pd.DataFrame, tf: Timeframe, left: int = 2, right: int = 2) -> tuple[TimeframeTrend, float]:
    """Return (TimeframeTrend, directional_score in [-1, 1]) for one timeframe."""
    high, low, close = df["high"], df["low"], df["close"]
    is_high, is_low = swing_points(high, low, left, right)

    sh = high[is_high]
    sl = low[is_low]
    last_close = float(close.iloc[-1])
    last_sh = float(sh.iloc[-1]) if len(sh) else None
    last_sl = float(sl.iloc[-1]) if len(sl) else None

    trend = Bias.NEUTRAL
    if len(sh) >= 2 and len(sl) >= 2:
        hh, hl = sh.iloc[-1] > sh.iloc[-2], sl.iloc[-1] > sl.iloc[-2]
        lh, ll = sh.iloc[-1] < sh.iloc[-2], sl.iloc[-1] < sl.iloc[-2]
        if hh and hl:
            trend = Bias.BULLISH
        elif lh and ll:
            trend = Bias.BEARISH

    bullish_break = last_sh is not None and last_close > last_sh
    bearish_break = last_sl is not None and last_close < last_sl

    # BOS continues the prevailing trend; CHOCH breaks it (early-reversal signal).
    bos = (trend is Bias.BULLISH and bullish_break) or (trend is Bias.BEARISH and bearish_break)
    choch = (trend is Bias.BULLISH and bearish_break) or (trend is Bias.BEARISH and bullish_break)

    score = trend.sign * 0.6
    if bos:
        score += 0.4 * trend.sign
    if choch:
        score = 0.5 * (-trend.sign)  # reversal in progress: lean the other way, modestly
    elif bullish_break and trend is Bias.NEUTRAL:
        score = 0.4
    elif bearish_break and trend is Bias.NEUTRAL:
        score = -0.4
    score = max(-1.0, min(1.0, score))

    return (
        TimeframeTrend(
            timeframe=tf,
            trend=trend,
            last_swing_high=round(last_sh, 4) if last_sh else None,
            last_swing_low=round(last_sl, 4) if last_sl else None,
            bos=bos,
            choch=choch,
        ),
        score,
    )


def _fair_value_gaps(df: pd.DataFrame, tf: Timeframe, lookback: int = 60, max_out: int = 4) -> list[FairValueGap]:
    """Detect recent unmitigated 3-candle FVGs near current price."""
    high, low = df["high"].values, df["low"].values
    n = len(df)
    start = max(2, n - lookback)
    gaps: list[FairValueGap] = []
    for i in range(start, n):
        # Bullish imbalance: candle i's low is above candle i-2's high.
        if low[i] > high[i - 2]:
            top, bottom = float(low[i]), float(high[i - 2])
            mitigated = bool(low[i + 1 :].min() <= top) if i + 1 < n else False
            gaps.append(FairValueGap(timeframe=tf, direction=Bias.BULLISH, top=round(top, 4), bottom=round(bottom, 4), mitigated=mitigated))
        # Bearish imbalance: candle i's high is below candle i-2's low.
        elif high[i] < low[i - 2]:
            top, bottom = float(low[i - 2]), float(high[i])
            mitigated = bool(high[i + 1 :].max() >= bottom) if i + 1 < n else False
            gaps.append(FairValueGap(timeframe=tf, direction=Bias.BEARISH, top=round(top, 4), bottom=round(bottom, 4), mitigated=mitigated))
    # Prefer the most recent, unmitigated gaps.
    fresh = [g for g in gaps if not g.mitigated]
    return (fresh or gaps)[-max_out:]


def _order_blocks(df: pd.DataFrame, tf: Timeframe, lookback: int = 40) -> list[OrderBlock]:
    """Last opposite-color candle before the most recent impulsive break."""
    o, h, lw, c = (df[x].values for x in ("open", "high", "low", "close"))
    n = len(df)
    start = max(1, n - lookback)
    blocks: list[OrderBlock] = []
    # Bullish OB: last down candle before a strong up move.
    for i in range(n - 2, start, -1):
        if c[i] < o[i] and c[i + 1] > o[i + 1] and (c[i + 1] - o[i + 1]) > 0.8 * (h[i + 1] - lw[i + 1]):
            blocks.append(OrderBlock(timeframe=tf, direction=Bias.BULLISH, top=round(float(h[i]), 4), bottom=round(float(lw[i]), 4)))
            break
    # Bearish OB: last up candle before a strong down move.
    for i in range(n - 2, start, -1):
        if c[i] > o[i] and c[i + 1] < o[i + 1] and (o[i + 1] - c[i + 1]) > 0.8 * (h[i + 1] - lw[i + 1]):
            blocks.append(OrderBlock(timeframe=tf, direction=Bias.BEARISH, top=round(float(h[i]), 4), bottom=round(float(lw[i]), 4)))
            break
    return blocks


def _liquidity_pools(df: pd.DataFrame, max_out: int = 4) -> list[LiquidityPool]:
    high, low, close = df["high"], df["low"], df["close"]
    is_high, is_low = swing_points(high, low, 2, 2)
    last_close = float(close.iloc[-1])
    pools: list[LiquidityPool] = []
    for price in high[is_high].tail(max_out):
        pools.append(LiquidityPool(price=round(float(price), 4), kind="buyside", swept=last_close > float(price)))
    for price in low[is_low].tail(max_out):
        pools.append(LiquidityPool(price=round(float(price), 4), kind="sellside", swept=last_close < float(price)))
    return pools


def _premium_discount(df: pd.DataFrame) -> float | None:
    """Where price sits within the most recent dealing range (0=low, 1=high)."""
    high, low, close = df["high"], df["low"], df["close"]
    is_high, is_low = swing_points(high, low, 2, 2)
    sh = high[is_high]
    sl = low[is_low]
    if not len(sh) or not len(sl):
        return None
    rng_hi, rng_lo = float(sh.iloc[-1]), float(sl.iloc[-1])
    if rng_hi <= rng_lo:
        return None
    return max(0.0, min(1.0, (float(close.iloc[-1]) - rng_lo) / (rng_hi - rng_lo)))


class MarketStructureAgent(BaseAgent):
    name = AgentName.MARKET_STRUCTURE
    output_cls = MarketStructureOutput

    def analyze(self, ctx: MarketContext) -> AgentOutput:
        trends: list[TimeframeTrend] = []
        weighted_sum = 0.0
        weight_total = 0.0
        signs: list[int] = []

        for tf in (Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4):
            if not ctx.has(tf):
                continue
            tft, score = _analyze_timeframe(ctx.frame(tf), tf)
            trends.append(tft)
            w = _TF_WEIGHTS[tf]
            weighted_sum += w * score
            weight_total += w
            if abs(score) > 0.15:
                signs.append(1 if score > 0 else -1)

        if not trends:
            return self._degraded("no timeframes available", code="data_unavailable")

        alignment = weighted_sum / weight_total if weight_total else 0.0
        # Agreement = how unanimous the directional timeframes are.
        agreement = abs(sum(signs)) / len(signs) if signs else 0.0

        structural_bias = Bias.NEUTRAL
        if alignment > 0.20:
            structural_bias = Bias.BULLISH
        elif alignment < -0.20:
            structural_bias = Bias.BEARISH

        confidence = min(1.0, abs(alignment) * 1.1) * (0.5 + 0.5 * agreement)

        # Detail on the most decision-relevant timeframes.
        htf = Timeframe.H1 if ctx.has(Timeframe.H1) else (Timeframe.H4 if ctx.has(Timeframe.H4) else Timeframe.M15)
        ltf = Timeframe.M15 if ctx.has(Timeframe.M15) else Timeframe.M5
        fvgs = _fair_value_gaps(ctx.frame(htf), htf) + _fair_value_gaps(ctx.frame(ltf), ltf)
        obs = _order_blocks(ctx.frame(htf), htf)
        pools = _liquidity_pools(ctx.frame(ltf))
        prem_disc = _premium_discount(ctx.frame(htf))

        out = MarketStructureOutput(
            agent=self.name,
            bias=structural_bias,
            structural_bias=structural_bias,
            confidence=round(confidence, 3),
            timeframe_trends=trends,
            fair_value_gaps=fvgs,
            order_blocks=obs,
            liquidity_pools=pools,
            premium_discount=round(prem_disc, 3) if prem_disc is not None else None,
            mtf_alignment=round(alignment, 3),
            reasoning=self._explain(structural_bias, alignment, agreement, trends, prem_disc),
        )

        # Structural risk flags that the Decision Engine respects.
        if any(t.choch for t in trends if t.timeframe in (Timeframe.H1, Timeframe.H4)):
            out.add_flag("htf_choch", "Change of character on a higher timeframe — structure may be reversing.", Severity.WARNING)
        if structural_bias is Bias.BULLISH and prem_disc is not None and prem_disc > 0.7:
            out.add_flag("buying_in_premium", "Bullish bias but price is in premium — poor location for longs.", Severity.WARNING)
        if structural_bias is Bias.BEARISH and prem_disc is not None and prem_disc < 0.3:
            out.add_flag("selling_in_discount", "Bearish bias but price is in discount — poor location for shorts.", Severity.WARNING)

        return out

    @staticmethod
    def _explain(bias: Bias, alignment: float, agreement: float, trends: list[TimeframeTrend], pd_loc: float | None) -> str:
        parts = [f"Structural bias {bias.value} (MTF alignment {alignment:+.2f}, agreement {agreement:.0%})."]
        parts.append("Per-TF trend: " + ", ".join(f"{t.timeframe.value}={t.trend.value}{'/BOS' if t.bos else ''}{'/CHOCH' if t.choch else ''}" for t in trends) + ".")
        if pd_loc is not None:
            zone = "premium" if pd_loc > 0.6 else ("discount" if pd_loc < 0.4 else "equilibrium")
            parts.append(f"Price in {zone} of the dealing range ({pd_loc:.0%}).")
        return " ".join(parts)
