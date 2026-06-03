"""Agent 7 — Risk Manager.

The capital-preservation core. It is *not* a directional voter; it is a gate plus
a sizing calculator, and it runs deterministically (no LLM ever sizes a position).

Responsibilities
----------------
* **Circuit breakers** — daily drawdown, total drawdown, consecutive losses,
  max trades/day, max concurrent positions. Any breach => no new risk.
* **Position sizing** — fixed-fractional risk (default 0.5% equity) with an
  ATR-anchored stop, a partial-take-profit ladder, break-even trigger and a
  trailing-stop distance. Lot size is derived from the dollar risk and the stop
  distance, then floored to the broker lot step.
* **Reward:risk gate** — setups whose blended RR is below the configured minimum
  are rejected regardless of how good they look.

Gold contract assumptions (typical MT5 XAUUSD): 1.00 lot = 100 oz, so a $1 move
== $100 per lot. These live in module constants and are easy to override per broker.
"""

from __future__ import annotations

import math

from goldmind.config import Settings, get_settings
from goldmind.core.context import MarketContext
from goldmind.core.enums import AgentName, Bias, OrderSide, Severity
from goldmind.core.schemas import (
    AccountState,
    PositionSizing,
    RiskAssessment,
    RiskFlag,
    TakeProfit,
)
from goldmind.logging import get_logger

CONTRACT_SIZE = 100.0   # oz per 1.0 lot (XAUUSD)
LOT_STEP = 0.01
MIN_LOT = 0.01
MAX_LOT = 50.0


def _round_lot(volume: float) -> float:
    return math.floor(volume / LOT_STEP) * LOT_STEP


class RiskManager:
    name = AgentName.RISK_MANAGER

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.cfg = self.settings.risk
        self.log = get_logger("agent.risk_manager")

    # ---- circuit breakers ----
    def circuit_breaker(self, acct: AccountState) -> tuple[bool, str | None, list[RiskFlag]]:
        flags: list[RiskFlag] = []
        if acct.daily_pnl_pct <= -self.cfg.max_daily_drawdown:
            return True, f"Daily drawdown {acct.daily_pnl_pct:.2%} breached limit {-self.cfg.max_daily_drawdown:.2%}.", flags
        if acct.drawdown_pct >= self.cfg.max_total_drawdown:
            return True, f"Total drawdown {acct.drawdown_pct:.2%} breached limit {self.cfg.max_total_drawdown:.2%}.", flags
        if acct.consecutive_losses >= self.cfg.max_consecutive_losses:
            return True, f"{acct.consecutive_losses} consecutive losses >= limit {self.cfg.max_consecutive_losses}.", flags
        # Soft caps (reject the new trade but not a 'breaker' state).
        if acct.trades_today >= self.cfg.max_trades_per_day:
            return True, f"Daily trade cap reached ({acct.trades_today}/{self.cfg.max_trades_per_day}).", flags
        if acct.open_positions >= self.cfg.max_concurrent_positions:
            return True, f"Max concurrent positions reached ({acct.open_positions}/{self.cfg.max_concurrent_positions}).", flags
        # Early-warning flags (not blocking yet).
        if acct.daily_pnl_pct <= -0.6 * self.cfg.max_daily_drawdown:
            flags.append(RiskFlag(code="approaching_daily_dd", message="Approaching daily drawdown limit.", severity=Severity.WARNING, source=self.name))
        return False, None, flags

    # ---- sizing ----
    def size(self, symbol: str, direction: Bias, entry: float, atr: float, equity: float) -> PositionSizing:
        side = OrderSide.BUY if direction is Bias.BULLISH else OrderSide.SELL
        stop_distance = max(atr * self.cfg.default_atr_stop_mult, 1e-6)
        sl = entry - side.sign * stop_distance
        risk_amount = equity * self.cfg.max_risk_per_trade

        raw_lot = risk_amount / (stop_distance * CONTRACT_SIZE)
        lot = min(MAX_LOT, max(0.0, _round_lot(raw_lot)))
        actual_risk = lot * stop_distance * CONTRACT_SIZE

        tps: list[TakeProfit] = []
        for r, frac in zip(self.cfg.tp_r_multiples, self.cfg.tp_partials, strict=True):
            tp_price = entry + side.sign * stop_distance * r
            tps.append(TakeProfit(price=round(tp_price, 3), r_multiple=r, close_fraction=frac))

        blended_rr = sum(r * f for r, f in zip(self.cfg.tp_r_multiples, self.cfg.tp_partials, strict=True))
        be_price = entry + side.sign * stop_distance * self.cfg.break_even_at_r

        return PositionSizing(
            symbol=symbol,
            side=side,
            entry=round(entry, 3),
            stop_loss=round(sl, 3),
            take_profits=tps,
            lot_size=round(lot, 2),
            risk_amount=round(actual_risk, 2),
            risk_pct=round(actual_risk / equity, 5) if equity else 0.0,
            reward_risk=round(blended_rr, 2),
            stop_distance=round(stop_distance, 3),
            break_even_price=round(be_price, 3),
            trailing_distance=round(atr * self.cfg.trailing_atr_mult, 3),
        )

    # ---- top-level assessment ----
    def assess(self, ctx: MarketContext, direction: Bias, entry: float, atr: float) -> RiskAssessment:
        acct = ctx.account
        out = RiskAssessment(agent=self.name, account=acct, model="deterministic")

        if atr <= 0 or entry <= 0:
            out.approved = False
            out.rejection_reason = "Invalid entry/ATR for sizing."
            out.add_flag("invalid_sizing_inputs", out.rejection_reason, Severity.CRITICAL)
            return out

        broke, reason, warn_flags = self.circuit_breaker(acct)
        out.risk_flags.extend(warn_flags)
        if broke:
            out.approved = False
            out.circuit_breaker_active = True
            out.rejection_reason = reason
            out.confidence = 0.0
            out.reasoning = f"Risk gate BLOCKED: {reason}"
            out.add_flag("circuit_breaker", reason or "blocked", Severity.CRITICAL)
            return out

        if direction is Bias.NEUTRAL:
            out.approved = False
            out.rejection_reason = "No directional conviction to size."
            out.reasoning = out.rejection_reason
            return out

        sizing = self.size(ctx.symbol, direction, entry, atr, acct.equity)
        out.sizing = sizing

        if sizing.lot_size < MIN_LOT:
            out.approved = False
            out.rejection_reason = "Stop too wide: minimum lot would exceed the per-trade risk budget."
            out.add_flag("stop_too_wide", out.rejection_reason, Severity.WARNING)
            out.reasoning = out.rejection_reason
            return out

        if sizing.reward_risk < self.cfg.min_reward_risk:
            out.approved = False
            out.rejection_reason = f"Blended RR {sizing.reward_risk:.2f} < minimum {self.cfg.min_reward_risk:.2f}."
            out.add_flag("low_reward_risk", out.rejection_reason, Severity.WARNING)
            out.reasoning = out.rejection_reason
            return out

        out.approved = True
        out.confidence = 1.0
        out.reasoning = (
            f"Approved {sizing.side.value} {sizing.lot_size} lots @ ~{sizing.entry}, "
            f"SL {sizing.stop_loss} ({sizing.stop_distance} pts = {self.cfg.default_atr_stop_mult}xATR), "
            f"risk ${sizing.risk_amount} ({sizing.risk_pct:.2%}), blended RR {sizing.reward_risk}. "
            f"BE at {sizing.break_even_price}, trail {sizing.trailing_distance}."
        )
        return out
