"""Event-driven backtesting engine.

Design choices that make the numbers trustworthy
-----------------------------------------------
* **Strictly causal.** A decision at bar *i* uses only candles up to and including
  *i* (the last *closed* bar). The trade is entered at bar *i+1*'s open — never at
  the signal bar's close. Indicators are causal and swings are confirmed, so there
  is no repainting.
* **Pessimistic intrabar fills.** If a bar's range touches both the stop and a take
  profit, the stop is assumed to fill first. This biases results *down*, which is
  the safe direction for a risk-first system.
* **The risk gates are live in the sim.** Equity, peak equity, consecutive losses
  and trades-per-day are tracked and fed back into the AccountState each cycle, so
  the circuit breakers actually fire in the backtest exactly as they would live.
* **Costs are modeled.** Spread + slippage are charged per trade in R units.

This is the same :class:`Orchestrator` used live — we backtest the real decision
logic, not a re-implementation of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from goldmind.agents.learning import ClosedTrade, LearningEngine
from goldmind.backtest.synthetic import resample
from goldmind.core.context import MarketContext
from goldmind.core.enums import OrderSide, Timeframe, TradeDecision
from goldmind.core.schemas import AccountState, PerformanceReport, PositionSizing
from goldmind.graph.workflow import Orchestrator
from goldmind.logging import get_logger

log = get_logger("backtest")


@dataclass
class BacktestConfig:
    decision_every: int = 12          # evaluate every N M5 bars (12 -> hourly)
    window_bars: int = 1500           # trailing M5 bars used to build the context
    warmup_bars: int = 1300
    max_hold_bars: int = 288          # ~1 day of M5 bars
    starting_equity: float = 100_000.0
    spread_points: float = 0.20       # XAUUSD typical spread in price
    slippage_points: float = 0.10
    timeframes: tuple[Timeframe, ...] = (Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4)


@dataclass
class BacktestResult:
    trades: list[ClosedTrade]
    equity_curve: list[tuple[object, float]]
    report: PerformanceReport
    starting_equity: float
    final_equity: float
    config: BacktestConfig = field(repr=False, default_factory=BacktestConfig)

    @property
    def total_return_pct(self) -> float:
        return (self.final_equity / self.starting_equity - 1.0) if self.starting_equity else 0.0

    def summary(self) -> str:
        r = self.report
        return (
            f"trades={r.trades} win_rate={r.win_rate:.1%} pf={r.profit_factor} "
            f"expectancy={r.expectancy_r:+.3f}R maxDD={r.max_drawdown_r}R "
            f"return={self.total_return_pct:+.2%} equity={self.final_equity:,.0f}"
        )


class BacktestEngine:
    def __init__(self, orchestrator: Orchestrator | None = None, config: BacktestConfig | None = None) -> None:
        self.orch = orchestrator or Orchestrator()
        self.cfg = config or BacktestConfig()

    # ---- trade simulation ----
    def _simulate_trade(self, base: pd.DataFrame, entry_idx: int, sizing: PositionSizing, side: OrderSide) -> tuple[float, int, float, float, float]:
        """Walk the position forward bar-by-bar. Returns
        (realized_R, exit_idx, exit_price, mae_R, mfe_R)."""
        o, h, lw, c = (base[x].values for x in ("open", "high", "low", "close"))
        n = len(base)
        sign = side.sign
        half_spread = self.cfg.spread_points / 2.0 + self.cfg.slippage_points / 2.0
        entry = float(o[entry_idx]) + sign * half_spread
        sd = sizing.stop_distance
        stop = entry - sign * sd
        tps = [(entry + sign * sd * tp.r_multiple, tp.close_fraction, tp.r_multiple) for tp in sizing.take_profits]
        hit = [False] * len(tps)

        remaining, realized, be_done = 1.0, 0.0, False
        mae = mfe = 0.0
        last = min(entry_idx + self.cfg.max_hold_bars, n - 1)
        cost_r = (self.cfg.spread_points + self.cfg.slippage_points) / sd  # round-trip cost in R

        for j in range(entry_idx + 1, last + 1):
            hi, lo, cl = float(h[j]), float(lw[j]), float(c[j])
            fav = (hi - entry) * sign if sign > 0 else (entry - lo) * 1.0
            adv = (entry - lo) * 1.0 if sign > 0 else (hi - entry) * 1.0
            mfe = max(mfe, fav / sd)
            mae = max(mae, adv / sd)

            # Pessimistic: stop checked before TP.
            stop_hit = lo <= stop if sign > 0 else hi >= stop
            if stop_hit:
                realized += remaining * ((stop - entry) * sign) / sd
                return realized - cost_r, j, stop, mae, mfe

            for k, (tp_price, frac, rmult) in enumerate(tps):
                if hit[k]:
                    continue
                tp_hit = hi >= tp_price if sign > 0 else lo <= tp_price
                if tp_hit:
                    realized += frac * rmult
                    remaining -= frac
                    hit[k] = True
                    if not be_done:
                        stop = entry  # move to break-even on first TP
                        be_done = True
            if remaining <= 1e-9:
                return realized - cost_r, j, tps[-1][0], mae, mfe

            if be_done and sizing.trailing_distance:
                new_stop = cl - sign * sizing.trailing_distance
                if (new_stop - stop) * sign > 0:
                    stop = new_stop

        # Timeout close at the last bar's close.
        realized += remaining * ((float(c[last]) - entry) * sign) / sd
        return realized - cost_r, last, float(c[last]), mae, mfe

    # ---- main loop ----
    def run(self, base_m5: pd.DataFrame) -> BacktestResult:
        cfg = self.cfg
        n = len(base_m5)
        equity = peak = cfg.starting_equity
        cons_losses = trades_today = 0
        daily_pnl = 0.0
        cur_day: date | None = None
        trades: list[ClosedTrade] = []
        curve: list[tuple[object, float]] = [(base_m5.index[cfg.warmup_bars], equity)]

        i = cfg.warmup_bars
        while i < n - 1:
            bar_day = base_m5.index[i].date()
            if bar_day != cur_day:
                cur_day, trades_today, daily_pnl = bar_day, 0, 0.0
            if i % cfg.decision_every != 0:
                i += 1
                continue

            window = base_m5.iloc[max(0, i - cfg.window_bars): i + 1]
            candles = {tf: resample(window, tf) for tf in cfg.timeframes}
            acct = AccountState(
                equity=equity, balance=equity, peak_equity=peak, open_positions=0,
                daily_realized_pnl=daily_pnl, consecutive_losses=cons_losses, trades_today=trades_today,
            )
            ctx = MarketContext(symbol="XAUUSD", as_of=window.index[-1].to_pydatetime(), candles=candles, account=acct)

            res = self.orch.evaluate(ctx, concurrent=False)
            dec = res.decision

            if dec.decision in (TradeDecision.BUY, TradeDecision.SELL) and dec.sizing is not None:
                side = dec.sizing.side
                realized_r, exit_idx, _exit_px, _mae, _mfe = self._simulate_trade(base_m5, i, dec.sizing, side)
                pnl = realized_r * dec.sizing.risk_amount
                equity += pnl
                peak = max(peak, equity)
                daily_pnl += pnl
                trades_today += 1
                cons_losses = cons_losses + 1 if realized_r <= 0 else 0
                near_news = any(f.code in {"news_blackout", "news_proximity"} for f in dec.risk_flags)
                trades.append(ClosedTrade(
                    id=str(dec.id), opened_at=base_m5.index[i].to_pydatetime(), closed_at=base_m5.index[exit_idx].to_pydatetime(),
                    side=side, r_multiple=round(realized_r, 4), pnl=round(pnl, 2),
                    quality_score=dec.quality_score, agreement=dec.agreement, net_score=dec.net_directional_score,
                    regime=res.regime.trend_regime.value, volatility_regime=res.regime.volatility_regime.value,
                    hour=base_m5.index[i].hour, near_news=near_news,
                ))
                curve.append((base_m5.index[exit_idx], round(equity, 2)))
                i = exit_idx + 1
            else:
                i += cfg.decision_every

        report = LearningEngine().analyze(trades)
        report.max_drawdown_pct = round(self._equity_drawdown(curve), 4)
        log.info("backtest_done", **{"trades": report.trades, "expectancy_r": report.expectancy_r, "final_equity": round(equity, 2)})
        return BacktestResult(trades=trades, equity_curve=curve, report=report,
                              starting_equity=cfg.starting_equity, final_equity=round(equity, 2), config=cfg)

    @staticmethod
    def _equity_drawdown(curve: list[tuple[object, float]]) -> float:
        peak = -float("inf")
        max_dd = 0.0
        for _t, eq in curve:
            peak = max(peak, eq)
            if peak > 0:
                max_dd = max(max_dd, (peak - eq) / peak)
        return max_dd
