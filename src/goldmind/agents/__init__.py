"""The ten agents. Import the registry helper to build a full agent set."""

from goldmind.agents.base import BaseAgent
from goldmind.agents.registry import build_analytical_agents, build_suite

__all__ = ["BaseAgent", "build_analytical_agents", "build_suite"]
