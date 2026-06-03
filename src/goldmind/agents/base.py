"""BaseAgent — common machinery for all analytical agents.

Every agent inherits: latency timing, structured logging, and — most importantly
— **fail-safe degradation**. A single agent throwing must never crash the graph
or, worse, be silently treated as a confident signal. On error the agent returns
a neutral, zero-confidence output carrying a CRITICAL risk flag, so the Decision
Engine sees "no information here" rather than a wrong opinion.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from time import perf_counter

from goldmind.config import Settings, get_settings
from goldmind.core.context import MarketContext
from goldmind.core.enums import AgentName, Bias, Severity
from goldmind.core.exceptions import DataUnavailableError
from goldmind.core.schemas import AgentOutput
from goldmind.logging import get_logger


class BaseAgent(ABC):
    #: Stable identifier (set by each subclass).
    name: AgentName
    #: Concrete output type the agent produces (an AgentOutput subclass).
    output_cls: type[AgentOutput] = AgentOutput

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.log = get_logger(f"agent.{self.name}")

    # --- subclasses implement this only ---
    @abstractmethod
    def analyze(self, ctx: MarketContext) -> AgentOutput:
        """Produce this agent's opinion. May raise; ``run`` handles failures."""

    # --- orchestrator entry point ---
    def run(self, ctx: MarketContext) -> AgentOutput:
        t0 = perf_counter()
        try:
            out = self.analyze(ctx)
        except DataUnavailableError as exc:
            self.log.warning("data_unavailable", error=str(exc))
            out = self._degraded(f"data unavailable: {exc}", code="data_unavailable")
        except Exception as exc:
            self.log.exception("agent_failed", error=str(exc))
            out = self._degraded(str(exc), code="agent_error", severity=Severity.CRITICAL)
        out.latency_ms = round((perf_counter() - t0) * 1000.0, 2)
        self.log.info(
            "agent_done",
            bias=str(out.bias),
            confidence=round(out.confidence, 3),
            latency_ms=out.latency_ms,
            flags=[f.code for f in out.risk_flags],
        )
        return out

    # --- helpers ---
    def _degraded(self, message: str, *, code: str, severity: Severity = Severity.WARNING) -> AgentOutput:
        out = self.output_cls(agent=self.name, bias=Bias.NEUTRAL, confidence=0.0, error=message)
        out.reasoning = f"Degraded output ({code}): {message}. Treated as no-information."
        out.add_flag(code, message, severity)
        return out

    def new_output(self, **kwargs) -> AgentOutput:
        """Construct the agent's typed output with its name pre-filled."""
        kwargs.setdefault("agent", self.name)
        return self.output_cls(**kwargs)
