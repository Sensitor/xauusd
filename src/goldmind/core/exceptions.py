"""Typed exceptions. A small, explicit hierarchy makes failure handling and
observability (which errors page a human vs. which degrade gracefully) clean.
"""

from __future__ import annotations


class GoldMindError(Exception):
    """Base class for every error raised by the system."""


class ConfigError(GoldMindError):
    """Invalid or missing configuration."""


class DataUnavailableError(GoldMindError):
    """A required data input (candles, news, macro series) could not be sourced.

    Agents should treat this as a reason to *abstain* (low confidence / NO_TRADE),
    never as a reason to guess.
    """


class AgentError(GoldMindError):
    """An agent failed internally. The orchestrator records it as a risk flag and
    continues with reduced information rather than crashing the whole graph."""

    def __init__(self, agent: str, message: str) -> None:
        super().__init__(f"[{agent}] {message}")
        self.agent = agent


class RiskRejection(GoldMindError):
    """Raised/returned when a trade violates a hard risk rule. This is a *normal*
    control-flow outcome, not a bug — capital preservation working as intended."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(f"{rule}: {message}")
        self.rule = rule


class BrokerConnectionError(GoldMindError):
    """Cannot reach the MT5 terminal / broker."""


class ExecutionError(GoldMindError):
    """Order placement, modification, or close failed at the broker."""

    def __init__(self, message: str, retcode: int | None = None) -> None:
        super().__init__(message)
        self.retcode = retcode
