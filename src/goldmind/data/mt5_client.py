"""Low-level MetaTrader 5 connectivity.

MetaTrader5 is a Windows-only C-extension, so it is imported **lazily**: the rest
of GoldMind (research, backtests, the analytical agents, CI) runs anywhere, and
only the execution node needs the terminal. Every public method raises a typed
``BrokerConnectionError`` / ``ExecutionError`` instead of leaking raw MT5 codes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from goldmind.config import Settings, get_settings
from goldmind.core.context import OHLCV_COLUMNS
from goldmind.core.enums import Timeframe
from goldmind.core.exceptions import BrokerConnectionError, ExecutionError
from goldmind.core.schemas import AccountState
from goldmind.logging import get_logger

log = get_logger("mt5")


def _import_mt5() -> Any:
    try:
        import MetaTrader5 as mt5  # type: ignore
    except Exception as exc:  # pragma: no cover - platform dependent
        raise BrokerConnectionError(
            "MetaTrader5 package not available. Install requirements-mt5.txt on the "
            "Windows/Wine execution node."
        ) from exc
    return mt5


class MT5Client:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._mt5: Any | None = None
        self._connected = False

    @property
    def mt5(self) -> Any:
        if self._mt5 is None:
            self._mt5 = _import_mt5()
        return self._mt5

    def _tf_const(self, tf: Timeframe) -> Any:
        return getattr(self.mt5, f"TIMEFRAME_{tf.value}")

    # ---- lifecycle ----
    def connect(self) -> None:
        s = self.settings
        kwargs: dict[str, Any] = {}
        if s.mt5_terminal_path:
            kwargs["path"] = s.mt5_terminal_path
        if s.mt5_login:
            kwargs.update(login=int(s.mt5_login), password=s.mt5_password, server=s.mt5_server)
        if not self.mt5.initialize(**kwargs):
            raise BrokerConnectionError(f"MT5 initialize failed: {self.mt5.last_error()}")
        if not self.mt5.symbol_select(s.mt5_symbol, True):
            raise BrokerConnectionError(f"Could not select symbol {s.mt5_symbol}")
        self._connected = True
        log.info("mt5_connected", server=s.mt5_server, symbol=s.mt5_symbol)

    def shutdown(self) -> None:
        if self._mt5 is not None and self._connected:
            self._mt5.shutdown()
            self._connected = False

    def __enter__(self) -> MT5Client:
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.shutdown()

    # ---- data ----
    def copy_rates(self, tf: Timeframe, count: int = 500, symbol: str | None = None) -> pd.DataFrame:
        sym = symbol or self.settings.mt5_symbol
        rates = self.mt5.copy_rates_from_pos(sym, self._tf_const(tf), 0, count)
        if rates is None or len(rates) == 0:
            raise ExecutionError(f"No rates returned for {sym} {tf}")
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.rename(columns={"tick_volume": "volume"}).set_index("time")
        for col in OHLCV_COLUMNS:
            if col not in df.columns:
                df[col] = 0.0
        return df[OHLCV_COLUMNS]

    def tick(self, symbol: str | None = None) -> tuple[float, float]:
        sym = symbol or self.settings.mt5_symbol
        t = self.mt5.symbol_info_tick(sym)
        if t is None:
            raise ExecutionError(f"No tick for {sym}")
        return float(t.bid), float(t.ask)

    def account_state(self) -> AccountState:
        info = self.mt5.account_info()
        if info is None:
            raise BrokerConnectionError("account_info() returned None")
        equity = float(info.equity)
        return AccountState(
            equity=equity,
            balance=float(info.balance),
            currency=info.currency,
            peak_equity=equity,  # peak is tracked in the DB; broker only knows 'now'
            open_positions=int(self.mt5.positions_total() or 0),
        )

    # ---- orders ----
    def order_send(self, request: dict[str, Any]) -> Any:
        result = self.mt5.order_send(request)
        if result is None:
            raise ExecutionError(f"order_send returned None: {self.mt5.last_error()}")
        if result.retcode != self.mt5.TRADE_RETCODE_DONE:
            raise ExecutionError(f"order rejected: retcode={result.retcode} {result.comment}", retcode=result.retcode)
        return result

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)
