# Data directory

Market data and artifacts live here. The contents are git-ignored (see
`.gitignore`) — never commit raw price dumps, model weights, or screenshots.

```
data/
  raw/         # raw vendor downloads (CSV/parquet) — ignored
  processed/   # cleaned/feature data — ignored
  cache/       # transient caches — ignored
screenshots/
  inbound/     # chart images for the Vision agent — ignored
```

## Backtesting on real history

Place an M5 OHLCV CSV (columns: `time,open,high,low,close,volume`, UTC timestamps)
and run:

```bash
python -m goldmind.backtest.run --csv data/raw/xauusd_m5.csv
python -m goldmind.backtest.run --csv data/raw/xauusd_m5.csv --walk-forward
```

Without `--csv`, the backtester generates synthetic data (plumbing validation
only — synthetic results are **not** evidence of edge).

## Sourcing XAUUSD data

- MetaTrader 5 `copy_rates_*` (the execution node already has this wired in
  `goldmind.data.mt5_client`).
- Dukascopy / HistData free tick & bar archives.
- Commercial vendors (Polygon, Tiingo, etc.) for higher quality.
