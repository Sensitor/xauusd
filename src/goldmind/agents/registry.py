"""Factory helpers that assemble the agent set.

Keeping construction in one place means the graph, the API, the backtester, and
tests all instantiate agents identically (same settings, same wiring).
"""

from __future__ import annotations

from dataclasses import dataclass

from goldmind.agents.base import BaseAgent
from goldmind.agents.chart_vision import ChartVisionAgent
from goldmind.agents.decision_engine import DecisionEngine
from goldmind.agents.learning import LearningEngine
from goldmind.agents.macro import MacroAgent
from goldmind.agents.market_regime import MarketRegimeAgent
from goldmind.agents.market_structure import MarketStructureAgent
from goldmind.agents.news_sentiment import NewsSentimentAgent
from goldmind.agents.risk_manager import RiskManager
from goldmind.agents.technical import TechnicalAgent
from goldmind.config import Settings, get_settings
from goldmind.core.enums import AgentName

# The six directional voters, in decision-weight order.
ANALYTICAL_AGENT_CLASSES: tuple[type[BaseAgent], ...] = (
    MarketStructureAgent,
    TechnicalAgent,
    MacroAgent,
    NewsSentimentAgent,
    ChartVisionAgent,
    MarketRegimeAgent,
)


def build_analytical_agents(settings: Settings | None = None) -> dict[AgentName, BaseAgent]:
    s = settings or get_settings()
    agents = [cls(s) for cls in ANALYTICAL_AGENT_CLASSES]
    return {a.name: a for a in agents}


@dataclass
class AgentSuite:
    """All components needed to run one evaluation -> decision -> (optional) execution."""

    analytical: dict[AgentName, BaseAgent]
    risk_manager: RiskManager
    decision_engine: DecisionEngine
    learning_engine: LearningEngine

    @property
    def regime_agent(self) -> BaseAgent:
        return self.analytical[AgentName.MARKET_REGIME]


def build_suite(settings: Settings | None = None) -> AgentSuite:
    s = settings or get_settings()
    return AgentSuite(
        analytical=build_analytical_agents(s),
        risk_manager=RiskManager(s),
        decision_engine=DecisionEngine(s),
        learning_engine=LearningEngine(),
    )
