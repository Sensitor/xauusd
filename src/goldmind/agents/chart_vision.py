"""Agent 5 — Chart Vision Agent.

Uses a multimodal model to read a TradingView-style screenshot the way a human
technician would: overall trend, key support/resistance, liquidity zones, and
classic patterns (double top/bottom, H&S and inverse, flags, triangles,
breakouts). It is a *corroborating* voice (10% weight) — useful because it sees
visual context (trendlines, channels) the numeric agents don't, but it never
drives a decision alone.

Abstains cleanly when no screenshot is provided or no vision model is configured.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from goldmind.agents.base import BaseAgent
from goldmind.core.context import MarketContext
from goldmind.core.enums import AgentName, Bias, Severity
from goldmind.core.schemas import AgentOutput, ChartPattern, ChartVisionOutput
from goldmind.llm import complete_structured, get_chat_model, resolve_model

_KNOWN_PATTERNS = (
    "double_top, double_bottom, head_and_shoulders, inverse_head_and_shoulders, "
    "bull_flag, bear_flag, ascending_triangle, descending_triangle, symmetrical_triangle, "
    "breakout, breakdown, range, channel"
)

_SYSTEM = (
    "You are an expert price-action technician analyzing a GOLD (XAUUSD) chart "
    f"screenshot. Identify the dominant trend, the most important horizontal "
    f"support/resistance levels (as numeric prices you can read from the axis), "
    f"liquidity zones, and any of these patterns if clearly present: {_KNOWN_PATTERNS}. "
    "Only report a pattern you can actually see; do not hallucinate. Provide a "
    "confidence in [0,1] reflecting clarity. List concrete risk areas (e.g. "
    "'price into prior supply at 2360'). If the image is unreadable, return neutral "
    "with low confidence."
)


class _VisionLLM(BaseModel):
    detected_trend: Bias
    patterns: list[ChartPattern] = Field(default_factory=list)
    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)
    risk_areas: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class ChartVisionAgent(BaseAgent):
    name = AgentName.CHART_VISION
    output_cls = ChartVisionOutput

    def analyze(self, ctx: MarketContext) -> AgentOutput:
        if not ctx.screenshot_path:
            return self._degraded("no chart screenshot supplied", code="no_chart_image", severity=Severity.INFO)

        model = get_chat_model("vision", self.settings)
        if model is None:
            return self._degraded("no vision model/key configured", code="vision_unavailable", severity=Severity.INFO)

        human = (
            "Analyze this XAUUSD chart. Return detected_trend, patterns (name, "
            "direction, confidence), support_levels, resistance_levels, risk_areas, "
            "overall confidence, and reasoning."
        )
        res: _VisionLLM = complete_structured(model, _VisionLLM, _SYSTEM, human, image_path=ctx.screenshot_path)

        out = ChartVisionOutput(
            agent=self.name,
            bias=res.detected_trend,
            confidence=round(res.confidence, 3),
            reasoning=res.reasoning,
            detected_trend=res.detected_trend,
            patterns=res.patterns,
            support_levels=[round(x, 4) for x in res.support_levels][:6],
            resistance_levels=[round(x, 4) for x in res.resistance_levels][:6],
            risk_areas=res.risk_areas[:6],
            image_ref=ctx.screenshot_path,
            model=resolve_model("vision", self.settings)[1],
        )
        # Reversal patterns against a trade are worth flagging.
        for p in res.patterns:
            if p.name.lower() in {"double_top", "head_and_shoulders"} and p.confidence > 0.6:
                out.add_flag("bearish_reversal_pattern", f"Vision sees {p.name} (conf {p.confidence:.0%}).", Severity.WARNING)
            if p.name.lower() in {"double_bottom", "inverse_head_and_shoulders"} and p.confidence > 0.6:
                out.add_flag("bullish_reversal_pattern", f"Vision sees {p.name} (conf {p.confidence:.0%}).", Severity.INFO)
        return out
