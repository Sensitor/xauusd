"""CLI entry point for backtests and walk-forward analysis.

Examples
--------
    python -m goldmind.backtest.run --bars 8000 --drift 0.00010
    python -m goldmind.backtest.run --walk-forward --bars 16000
    python -m goldmind.backtest.run --csv data/xauusd_m5.csv

CSV format: a timestamped OHLCV file with columns time,open,high,low,close,volume.
"""

from __future__ import annotations

import argparse

import pandas as pd

from goldmind.backtest.engine import BacktestConfig, BacktestEngine
from goldmind.backtest.synthetic import generate_ohlcv
from goldmind.backtest.walk_forward import WalkForwardAnalysis, WalkForwardConfig
from goldmind.logging import configure_logging


def _load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    time_col = next((c for c in df.columns if c.lower() in ("time", "timestamp", "date", "datetime")), df.columns[0])
    df[time_col] = pd.to_datetime(df[time_col], utc=True)
    df = df.set_index(time_col).rename(columns=str.lower)
    return df[["open", "high", "low", "close", "volume"]]


def main() -> None:
    p = argparse.ArgumentParser(description="GoldMind backtester")
    p.add_argument("--csv", help="Path to an M5 OHLCV CSV. If omitted, synthetic data is generated.")
    p.add_argument("--bars", type=int, default=8000, help="Synthetic M5 bars to generate.")
    p.add_argument("--drift", type=float, default=0.00008, help="Synthetic per-bar drift.")
    p.add_argument("--volatility", type=float, default=0.0008, help="Synthetic per-bar volatility.")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--equity", type=float, default=100_000.0)
    p.add_argument("--decision-every", type=int, default=12, help="Evaluate every N M5 bars.")
    p.add_argument("--walk-forward", action="store_true", help="Run walk-forward instead of a single backtest.")
    args = p.parse_args()
    configure_logging("INFO")

    base = _load_csv(args.csv) if args.csv else generate_ohlcv(args.bars, drift=args.drift, volatility=args.volatility, seed=args.seed)
    print(f"Loaded {len(base)} M5 bars: {base.index[0]} -> {base.index[-1]}")

    if args.walk_forward:
        result = WalkForwardAnalysis(WalkForwardConfig()).run(base)
        print("\n" + result.summary())
        return

    cfg = BacktestConfig(starting_equity=args.equity, decision_every=args.decision_every)
    result = BacktestEngine(config=cfg).run(base)
    print("\n=== BACKTEST RESULT ===")
    print(result.summary())
    r = result.report
    print(f"\nProfit factor: {r.profit_factor} | Sharpe(trade): {r.sharpe} | Sortino(trade): {r.sortino}")
    print(f"Avg win: {r.avg_win_r}R | Avg loss: {r.avg_loss_r}R | Max DD: {r.max_drawdown_pct:.2%} ({r.max_drawdown_r}R)")
    if r.insights:
        print("\nLearning insights:")
        for ins in r.insights:
            print(f"  [{ins.category}] {ins.statement}")
    print("\nNOTE: synthetic data validates plumbing only — never mistake it for edge.")


if __name__ == "__main__":
    main()
