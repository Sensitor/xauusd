"""Agent 10 — Learning Engine.

Closes the loop. It reads the realized trade ledger and turns it into (a) honest
performance statistics and (b) *actionable* insights that feed back into the
filters, the risk config, and the decision thresholds. The goal is not a prettier
report — it is to find, with evidence, the conditions under which the system has
edge and the conditions where it bleeds, then recommend tightening the latter.

It is intentionally model-light: the statistics are deterministic so they can be
trusted; an LLM can later *narrate* them, but the numbers come from the ledger.
"""

from __future__ import annotations

from datetime import datetime
from statistics import mean, pstdev

from pydantic import BaseModel, Field

from goldmind.core.enums import AgentName, OrderSide
from goldmind.core.schemas import LearningInsight, PerformanceReport
from goldmind.logging import get_logger

MIN_SAMPLES_FOR_INSIGHT = 12


class ClosedTrade(BaseModel):
    """A realized trade as the Learning Engine consumes it (DB-row shaped)."""

    id: str
    opened_at: datetime
    closed_at: datetime
    side: OrderSide
    r_multiple: float = Field(..., description="Realized profit in R (risk units). The core unit of analysis.")
    pnl: float = 0.0
    quality_score: float | None = None
    agreement: float | None = None
    net_score: float | None = None
    regime: str | None = None
    volatility_regime: str | None = None
    hour: int | None = None
    near_news: bool = False

    @property
    def is_win(self) -> bool:
        return self.r_multiple > 0


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def _max_drawdown_r(r_series: list[float]) -> float:
    equity, peak, max_dd = 0.0, 0.0, 0.0
    for r in r_series:
        equity += r
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


class LearningEngine:
    name = AgentName.LEARNING

    def __init__(self) -> None:
        self.log = get_logger("agent.learning")

    def analyze(self, trades: list[ClosedTrade]) -> PerformanceReport:
        if not trades:
            now = datetime.utcnow()
            return PerformanceReport(window_start=now, window_end=now, trades=0, win_rate=0.0, profit_factor=0.0, expectancy_r=0.0)

        trades = sorted(trades, key=lambda t: t.closed_at)
        rs = [t.r_multiple for t in trades]
        wins = [r for r in rs if r > 0]
        losses = [r for r in rs if r <= 0]

        gross_profit = sum(wins)
        gross_loss = -sum(losses)
        sd = pstdev(rs) if len(rs) > 1 else 0.0
        downside = [min(0.0, r) for r in rs]
        dsd = pstdev(downside) if len(downside) > 1 else 0.0

        report = PerformanceReport(
            window_start=trades[0].opened_at,
            window_end=trades[-1].closed_at,
            trades=len(trades),
            win_rate=round(_safe_div(len(wins), len(rs)), 4),
            # Profit factor is undefined with zero losses; report None (∞) rather
            # than a misleading 0.0.
            profit_factor=round(gross_profit / gross_loss, 3) if gross_loss > 0 else None,
            expectancy_r=round(mean(rs), 4),
            sharpe=round(_safe_div(mean(rs), sd), 3) if sd else None,        # per-trade Sharpe
            sortino=round(_safe_div(mean(rs), dsd), 3) if dsd else None,     # per-trade Sortino
            max_drawdown_pct=None,
            avg_win_r=round(mean(wins), 3) if wins else None,
            avg_loss_r=round(mean(losses), 3) if losses else None,
            max_drawdown_r=round(_max_drawdown_r(rs), 3),
        )

        best, worst = self._condition_breakdown(trades)
        report.best_conditions = best
        report.worst_conditions = worst
        report.insights = self._insights(trades, report, best, worst)
        self.log.info("learning_report", trades=report.trades, expectancy_r=report.expectancy_r,
                      profit_factor=report.profit_factor, insights=len(report.insights))
        return report

    # ---- condition mining ----
    def _condition_breakdown(self, trades: list[ClosedTrade]) -> tuple[dict, dict]:
        def group_expectancy(key) -> dict[str, dict]:
            groups: dict[str, list[float]] = {}
            for t in trades:
                k = key(t)
                if k is None:
                    continue
                groups.setdefault(str(k), []).append(t.r_multiple)
            return {k: {"n": len(v), "expectancy_r": round(mean(v), 3)} for k, v in groups.items() if len(v) >= 3}

        by_regime = group_expectancy(lambda t: t.regime)
        by_session = group_expectancy(lambda t: None if t.hour is None else f"{t.hour:02d}h")
        by_agreement = group_expectancy(lambda t: None if t.agreement is None else ("high_agree" if t.agreement >= 0.7 else "low_agree"))

        all_groups = {**{f"regime:{k}": v for k, v in by_regime.items()},
                      **{f"session:{k}": v for k, v in by_session.items()},
                      **{f"agreement:{k}": v for k, v in by_agreement.items()}}
        if not all_groups:
            return {}, {}
        best_key = max(all_groups, key=lambda k: all_groups[k]["expectancy_r"])
        worst_key = min(all_groups, key=lambda k: all_groups[k]["expectancy_r"])
        return {best_key: all_groups[best_key]}, {worst_key: all_groups[worst_key]}

    # ---- insights / recommendations ----
    def _insights(self, trades, report: PerformanceReport, best: dict, worst: dict) -> list[LearningInsight]:
        out: list[LearningInsight] = []

        if report.expectancy_r <= 0 and report.trades >= MIN_SAMPLES_FOR_INSIGHT:
            out.append(LearningInsight(category="selection", confidence=0.7,
                statement="Overall expectancy is non-positive — tighten entry filters or pause live risk.",
                evidence={"expectancy_r": report.expectancy_r, "trades": report.trades}))

        # Worst condition -> propose a filter.
        for key, stat in worst.items():
            if stat["expectancy_r"] < -0.1 and stat["n"] >= MIN_SAMPLES_FOR_INSIGHT // 2:
                out.append(LearningInsight(category="filter", confidence=0.6,
                    statement=f"Negative expectancy in {key} ({stat['expectancy_r']} R over {stat['n']} trades). Consider filtering it out.",
                    evidence={key: stat}))

        # Low-agreement trades underperforming -> raise the agreement gate.
        low = [t.r_multiple for t in trades if t.agreement is not None and t.agreement < 0.7]
        high = [t.r_multiple for t in trades if t.agreement is not None and t.agreement >= 0.7]
        if len(low) >= 8 and len(high) >= 8 and mean(low) < mean(high) - 0.2:
            out.append(LearningInsight(category="selection", confidence=0.65,
                statement="High-agreement trades materially outperform low-agreement ones. Raise min_agreement.",
                evidence={"low_agree_exp": round(mean(low), 3), "high_agree_exp": round(mean(high), 3)}))

        # News-proximal trades.
        news = [t.r_multiple for t in trades if t.near_news]
        if len(news) >= 6 and mean(news) < 0:
            out.append(LearningInsight(category="risk", confidence=0.6,
                statement="Trades near high-impact news lose on average. Widen the news blackout window.",
                evidence={"near_news_exp": round(mean(news), 3), "n": len(news)}))

        # Stops getting run (avg loss worse than -1R) -> entries/timing issue.
        if report.avg_loss_r is not None and report.avg_loss_r < -1.05:
            out.append(LearningInsight(category="risk", confidence=0.55,
                statement="Average loss exceeds 1R (slippage/gaps or stops too tight relative to entries).",
                evidence={"avg_loss_r": report.avg_loss_r}))

        # Edge decay: recent third vs. earlier.
        if report.trades >= 3 * MIN_SAMPLES_FOR_INSIGHT:
            third = report.trades // 3
            recent = mean([t.r_multiple for t in trades[-third:]])
            earlier = mean([t.r_multiple for t in trades[:third]])
            if recent < earlier - 0.2:
                out.append(LearningInsight(category="regime", confidence=0.5,
                    statement="Edge appears to be decaying (recent expectancy below earlier). Re-examine regime fit / re-optimize.",
                    evidence={"recent_exp": round(recent, 3), "earlier_exp": round(earlier, 3)}))

        if best:
            bk, bs = next(iter(best.items()))
            out.append(LearningInsight(category="selection", confidence=0.5,
                statement=f"Strongest edge in {bk} ({bs['expectancy_r']} R). Consider weighting toward it.",
                evidence={bk: bs}))
        return out
