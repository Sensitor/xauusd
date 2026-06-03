"""Walk-forward analysis.

Single-pass backtests overfit: you tune on the same data you report. Walk-forward
mitigates this by repeatedly (1) optimizing parameters on an *in-sample* (IS)
window, then (2) measuring performance on the immediately following, untouched
*out-of-sample* (OOS) window. Only the concatenated OOS results are reported —
that is the honest estimate of forward performance.

Here we sweep two high-leverage knobs (the Decision Engine's ``min_quality`` gate
and the Risk Manager's ATR stop multiple), but the harness is generic: pass any
parameter grid and a factory that turns a parameter dict into an Orchestrator.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import pandas as pd

from goldmind.agents.decision_engine import DecisionEngine
from goldmind.agents.learning import ClosedTrade, LearningEngine
from goldmind.agents.registry import AgentSuite, build_analytical_agents
from goldmind.agents.risk_manager import RiskManager
from goldmind.backtest.engine import BacktestConfig, BacktestEngine, BacktestResult
from goldmind.config import get_settings
from goldmind.core.schemas import PerformanceReport
from goldmind.graph.workflow import Orchestrator
from goldmind.logging import get_logger

log = get_logger("walk_forward")

Params = dict[str, float]


def default_orchestrator_factory(params: Params) -> Orchestrator:
    """Build an Orchestrator whose decision/risk knobs reflect ``params``."""
    settings = get_settings().model_copy(deep=True)
    settings.risk.default_atr_stop_mult = params.get("atr_stop_mult", settings.risk.default_atr_stop_mult)
    suite = AgentSuite(
        analytical=build_analytical_agents(settings),
        risk_manager=RiskManager(settings),
        decision_engine=DecisionEngine(settings, min_quality=params.get("min_quality", 60.0)),
        learning_engine=LearningEngine(),
    )
    return Orchestrator(suite, settings)


DEFAULT_GRID: dict[str, list[float]] = {
    "min_quality": [55.0, 62.0, 70.0],
    "atr_stop_mult": [1.2, 1.5],
}


@dataclass
class WalkForwardConfig:
    is_bars: int = 4000
    oos_bars: int = 1500
    min_trades_is: int = 8
    backtest: BacktestConfig = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.backtest is None:
            self.backtest = BacktestConfig(warmup_bars=1300, window_bars=1500)


@dataclass
class FoldResult:
    fold: int
    best_params: Params
    is_expectancy_r: float
    oos: BacktestResult


@dataclass
class WalkForwardResult:
    folds: list[FoldResult]
    combined_oos: PerformanceReport

    def summary(self) -> str:
        lines = ["Walk-forward OOS folds:"]
        for f in self.folds:
            lines.append(f"  fold {f.fold}: params={f.best_params} IS_exp={f.is_expectancy_r:+.3f}R -> OOS {f.oos.summary()}")
        c = self.combined_oos
        lines.append(f"COMBINED OOS: trades={c.trades} win_rate={c.win_rate:.1%} pf={c.profit_factor} expectancy={c.expectancy_r:+.3f}R")
        return "\n".join(lines)


def _grid(grid: dict[str, list[float]]) -> Iterable[Params]:
    keys = list(grid)
    for combo in itertools.product(*(grid[k] for k in keys)):
        yield dict(zip(keys, combo, strict=True))


class WalkForwardAnalysis:
    def __init__(
        self,
        config: WalkForwardConfig | None = None,
        grid: dict[str, list[float]] | None = None,
        orchestrator_factory: Callable[[Params], Orchestrator] = default_orchestrator_factory,
    ) -> None:
        self.cfg = config or WalkForwardConfig()
        self.grid = grid or DEFAULT_GRID
        self.factory = orchestrator_factory

    def run(self, base_m5: pd.DataFrame) -> WalkForwardResult:
        cfg = self.cfg
        n = len(base_m5)
        folds: list[FoldResult] = []
        combined_trades: list[ClosedTrade] = []

        start = 0
        fold_i = 0
        while start + cfg.is_bars + cfg.oos_bars <= n:
            is_slice = base_m5.iloc[start: start + cfg.is_bars]
            oos_slice = base_m5.iloc[start + cfg.is_bars - cfg.backtest.window_bars: start + cfg.is_bars + cfg.oos_bars]

            # 1) optimize on IS
            best_params, best_exp = None, -1e9
            for params in _grid(self.grid):
                res = BacktestEngine(self.factory(params), cfg.backtest).run(is_slice)
                if res.report.trades >= cfg.min_trades_is and res.report.expectancy_r > best_exp:
                    best_params, best_exp = params, res.report.expectancy_r
            if best_params is None:  # not enough IS trades for any param; skip fold
                start += cfg.oos_bars
                fold_i += 1
                continue

            # 2) evaluate the winner on OOS
            oos_res = BacktestEngine(self.factory(best_params), cfg.backtest).run(oos_slice)
            folds.append(FoldResult(fold=fold_i, best_params=best_params, is_expectancy_r=round(best_exp, 4), oos=oos_res))
            combined_trades.extend(oos_res.trades)
            log.info("wf_fold", fold=fold_i, params=best_params, oos_trades=oos_res.report.trades, oos_exp=oos_res.report.expectancy_r)

            start += cfg.oos_bars
            fold_i += 1

        combined = LearningEngine().analyze(combined_trades)
        return WalkForwardResult(folds=folds, combined_oos=combined)
