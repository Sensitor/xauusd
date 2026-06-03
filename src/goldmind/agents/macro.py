"""Agent 3 — Macro Analyst.

Forms a *gold-specific* macro bias from the rate/inflation/risk complex:
CPI, Core CPI, PPI, NFP, Unemployment, FOMC, Treasury yields, DXY, geopolitics.

Two execution paths:
  * **LLM path** (preferred): an instructed reasoning model synthesizes the
    indicators into a structured bias with explicit reasoning.
  * **Rule path** (fallback / offline / no-key): a transparent scoring of release
    surprises and the DXY/yields trend. Gold's well-established inverse links to
    real yields and the dollar are encoded directly.

The data layer is expected to populate ``ctx.raw['macro']`` with a digest and/or
a list of indicator dicts. With neither LLM nor data, the agent abstains.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from goldmind.agents.base import BaseAgent
from goldmind.core.context import MarketContext
from goldmind.core.enums import AgentName, Bias, RiskEnvironment, Severity
from goldmind.core.schemas import AgentOutput, MacroIndicator, MacroOutput
from goldmind.llm import complete_structured, get_chat_model, resolve_model

# Sign of gold's reaction to a *positive* surprise in each release.
# +1 => positive surprise is bullish for gold; -1 => bearish.
_SURPRISE_SIGN: dict[str, int] = {
    "cpi": -1, "core cpi": -1, "ppi": -1, "nfp": -1, "non-farm": -1,
    "retail sales": -1, "gdp": -1, "ism": -1, "pmi": -1,
    "unemployment": +1,  # higher unemployment => dovish => bullish gold
}

_SYSTEM = (
    "You are a senior macro strategist who trades GOLD (XAUUSD). Judge the macro "
    "backdrop ONLY as it affects gold. Core relationships: gold is inversely related "
    "to real yields and the US dollar (DXY); hot inflation/strong labor data is "
    "hawkish => higher yields/DXY => bearish gold short-term; dovish surprises and "
    "risk-off/geopolitical stress are bullish gold. Be decisive but calibrate "
    "confidence to the strength and freshness of the evidence. If evidence is thin, "
    "return neutral with low confidence. Never invent data."
)


class _MacroLLM(BaseModel):
    macro_bias: Bias
    risk_environment: RiskEnvironment
    dxy_trend: Bias = Bias.NEUTRAL
    yields_trend: Bias = Bias.NEUTRAL
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


def _parse_indicators(raw: Any) -> list[MacroIndicator]:
    out: list[MacroIndicator] = []
    for item in raw or []:
        if isinstance(item, MacroIndicator):
            out.append(item)
        elif isinstance(item, dict):
            out.append(MacroIndicator(**{k: item.get(k) for k in ("name", "value", "prior", "surprise", "gold_impact") if k in item}))
    return out


def _rule_based(indicators: list[MacroIndicator], dxy_trend: Bias, yields_trend: Bias, risk_env: RiskEnvironment) -> tuple[Bias, float, str]:
    score = 0.0
    reasons: list[str] = []
    for ind in indicators:
        name = ind.name.lower()
        sign = next((v for k, v in _SURPRISE_SIGN.items() if k in name), 0)
        if ind.gold_impact is not Bias.NEUTRAL:
            score += ind.gold_impact.sign * 0.5
            reasons.append(f"{ind.name}->{ind.gold_impact.value}")
        elif ind.surprise is not None and sign:
            contrib = sign * (1 if ind.surprise > 0 else -1) * 0.5
            score += contrib
            reasons.append(f"{ind.name} surprise {ind.surprise:+.2f} ({'bullish' if contrib > 0 else 'bearish'})")

    # DXY / yields up => bearish gold.
    score -= dxy_trend.sign * 0.6
    score -= yields_trend.sign * 0.6
    if dxy_trend is not Bias.NEUTRAL:
        reasons.append(f"DXY {dxy_trend.value}")
    if yields_trend is not Bias.NEUTRAL:
        reasons.append(f"yields {yields_trend.value}")
    if risk_env is RiskEnvironment.RISK_OFF:
        score += 0.7
        reasons.append("risk-off (haven bid)")
    elif risk_env is RiskEnvironment.RISK_ON:
        score -= 0.4
        reasons.append("risk-on")

    bias = Bias.BULLISH if score > 0.4 else (Bias.BEARISH if score < -0.4 else Bias.NEUTRAL)
    confidence = min(0.8, abs(score) / 2.0)  # rule path is capped below LLM ceiling
    text = "Rule-based macro: " + (", ".join(reasons) if reasons else "no decisive macro inputs") + f" => {bias.value}."
    return bias, confidence, text


class MacroAgent(BaseAgent):
    name = AgentName.MACRO
    output_cls = MacroOutput

    def analyze(self, ctx: MarketContext) -> AgentOutput:
        raw = ctx.raw.get("macro", {}) if isinstance(ctx.raw.get("macro"), dict) else {}
        indicators = _parse_indicators(raw.get("indicators"))
        dxy_trend = Bias(raw.get("dxy_trend", "neutral"))
        yields_trend = Bias(raw.get("yields_trend", "neutral"))
        risk_env = RiskEnvironment(raw.get("risk_environment", "neutral"))
        digest = raw.get("digest")

        model = get_chat_model("reasoning", self.settings)
        if model is not None and (digest or indicators):
            try:
                human = self._format_prompt(digest, indicators, dxy_trend, yields_trend, ctx)
                res: _MacroLLM = complete_structured(model, _MacroLLM, _SYSTEM, human)
                return self._build(res.macro_bias, res.confidence, res.reasoning, indicators,
                                   res.risk_environment, res.dxy_trend, res.yields_trend,
                                   model=resolve_model("reasoning", self.settings)[1])
            except Exception as exc:
                self.log.warning("macro_llm_failed", error=str(exc))

        if not indicators and dxy_trend is Bias.NEUTRAL and yields_trend is Bias.NEUTRAL and risk_env is RiskEnvironment.NEUTRAL:
            out = self._degraded("no macro data supplied", code="macro_data_unavailable", severity=Severity.INFO)
            return out

        bias, conf, text = _rule_based(indicators, dxy_trend, yields_trend, risk_env)
        return self._build(bias, conf, text, indicators, risk_env, dxy_trend, yields_trend, model="rule_based")

    def _build(self, bias, conf, reasoning, indicators, risk_env, dxy_trend, yields_trend, model) -> MacroOutput:
        out = MacroOutput(
            agent=self.name, bias=bias, confidence=round(float(conf), 3), reasoning=reasoning,
            macro_bias=bias, risk_environment=risk_env, dxy_trend=dxy_trend, yields_trend=yields_trend,
            indicators=indicators, model=model,
        )
        if risk_env is RiskEnvironment.RISK_OFF:
            out.add_flag("risk_off", "Risk-off backdrop supports gold but raises gap/volatility risk.", Severity.INFO)
        return out

    @staticmethod
    def _format_prompt(digest, indicators, dxy_trend, yields_trend, ctx) -> str:
        lines = [f"As of {ctx.as_of:%Y-%m-%d %H:%M} UTC, assess the macro bias for XAUUSD."]
        if digest:
            lines.append(f"Macro digest:\n{digest}")
        if indicators:
            lines.append("Recent releases:")
            for ind in indicators:
                lines.append(f"  - {ind.name}: value={ind.value} prior={ind.prior} surprise={ind.surprise}")
        lines.append(f"DXY trend: {dxy_trend.value}; Treasury yields trend: {yields_trend.value}.")
        lines.append("Return macro_bias, risk_environment, dxy/yields trend, confidence (0-1), and concise reasoning.")
        return "\n".join(lines)
