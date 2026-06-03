"""MarketContext — the immutable input bundle handed to every agent for one
evaluation cycle.

Heavy numeric series (OHLCV per timeframe) live here as pandas DataFrames rather
than in the Pydantic contracts so that the schemas stay JSON-clean and cheap to
serialize, while the agents get fast vectorized access to candles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pandas as pd

from goldmind.core.enums import Timeframe
from goldmind.core.schemas import AccountState

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


@dataclass(frozen=True)
class MarketContext:
    """One coherent view of the world at ``as_of``.

    Parameters
    ----------
    symbol:
        Instrument, always ``XAUUSD`` here but kept explicit for portability.
    as_of:
        The 'now' of this cycle. In live trading it is wall-clock; in backtests
        it is the simulated bar time. Agents MUST treat any data after ``as_of``
        as unavailable (the data layer is responsible for not leaking the future).
    candles:
        Mapping of timeframe -> DataFrame indexed by UTC timestamp with the
        canonical OHLCV columns. The last row is the most recent *closed* bar.
    account:
        Live account snapshot the Risk Manager sizes against.
    screenshot_path:
        Optional chart image for the Vision agent.
    raw:
        Free-form attachment slot (e.g. pre-fetched news/macro payloads) so the
        data layer can pass provider responses straight through to LLM agents.
    """

    symbol: str
    as_of: datetime
    candles: dict[Timeframe, pd.DataFrame]
    account: AccountState
    screenshot_path: str | None = None
    raw: dict[str, object] = field(default_factory=dict)

    def frame(self, tf: Timeframe) -> pd.DataFrame:
        """Return candles for ``tf`` or raise if absent (agents abstain on missing data)."""
        df = self.candles.get(tf)
        if df is None or df.empty:
            from goldmind.core.exceptions import DataUnavailableError

            raise DataUnavailableError(f"No candles for {self.symbol} {tf}")
        return df

    def has(self, tf: Timeframe) -> bool:
        df = self.candles.get(tf)
        return df is not None and not df.empty

    def last_close(self, tf: Timeframe = Timeframe.M5) -> float:
        return float(self.frame(tf)["close"].iloc[-1])

    def validate(self) -> None:
        """Cheap structural checks so a malformed feed fails fast, not mid-agent."""
        for tf, df in self.candles.items():
            missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
            if missing:
                from goldmind.core.exceptions import DataUnavailableError

                raise DataUnavailableError(f"{tf} frame missing columns: {missing}")

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)
