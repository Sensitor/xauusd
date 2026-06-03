"""GoldMind AI — institutional-grade multi-agent trading system for XAUUSD (Gold).

The package is intentionally importable without optional heavy dependencies
(MetaTrader5, psycopg, fastapi). Submodules that require them import lazily so
the research / analysis core stays usable in any environment.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
