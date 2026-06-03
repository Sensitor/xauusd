"""Agent 8 — Decision Engine.

Aggregates the six analytical voters into a single, explainable verdict. The
philosophy of the whole system lives here: **NO TRADE is the default and a valid
outcome.** A trade is emitted only when conviction, cross-agent agreement, and
setup quality clear regime-scaled thresholds *and* the Risk Manager approves *and*
no CRITICAL veto (news blackout, circuit breaker) is present.

Scoring
-------
* ``net_directional_score`` = Σ weightᵢ · (confidenceᵢ · directionᵢ)  ∈ [-1, 1]
* ``agreement``             = weighted fraction of voters aligned with the net sign
* ``quality_score`` (0–100) = 50·|net| + 30·agreement + 20·avg_confidence
* A trade requires ``quality_score ≥ min_quality · regime.quality_multiplier``,
  ``|net| ≥ min_net_score`` and ``agreement ≥ min_agreement``.

Every input vote and every gate outcome is recorded on the ``TradingDecision`` so
the dashboard and the Learning Engine can reconstruct *why* — not just *what*.
"""

from __future__ import annotations

from goldmind.config import Settings, get_settings
from goldmind.core.enums import (
    SCORING_AGENTS,
    AgentName,
    Bias,
    Severity,
    TradeDecision,
)
from goldmind.core.schemas import (
    AgentOutput,
    AgentVote,
    MarketRegimeOutput,
    RiskAssessment,
    RiskFlag,
    TradingDecision,
)
from goldmind.logging import get_logger

# Risk-flag codes that hard-veto a trade no matter how strong the vote.
DEFAULT_VETO_CODES = frozenset({"news_blackout", "circuit_breaker"})


def provisional_direction(outputs: dict[AgentName, AgentOutput], settings: Settings) -> tuple[Bias, float]:
    """Net direction from the analytical voters — used to size *before* the final
    decision (the Risk Manager needs a side to compute the stop)."""
    weights = settings.weights.scoring_weights()
    net = sum(weights[a] * outputs[a].signed_confidence for a in SCORING_AGENTS if a in outputs)
    direction = Bias.BULLISH if net > 0 else (Bias.BEARISH if net < 0 else Bias.NEUTRAL)
    return direction, net


class DecisionEngine:
    name = AgentName.DECISION_ENGINE

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        min_quality: float = 60.0,
        min_net_score: float = 0.25,
        min_agreement: float = 0.55,
        veto_codes: frozenset[str] = DEFAULT_VETO_CODES,
    ) -> None:
        self.settings = settings or get_settings()
        self.min_quality = min_quality
        self.min_net_score = min_net_score
        self.min_agreement = min_agreement
        self.veto_codes = veto_codes
        self.log = get_logger("agent.decision_engine")

    def decide(
        self,
        symbol: str,
        outputs: dict[AgentName, AgentOutput],
        risk: RiskAssessment,
        regime: MarketRegimeOutput | None = None,
    ) -> TradingDecision:
        weights = self.settings.weights.scoring_weights()

        votes: list[AgentVote] = []
        net = 0.0
        for agent in SCORING_AGENTS:
            o = outputs.get(agent)
            if o is None:
                continue
            w = weights[agent]
            contrib = w * o.signed_confidence
            net += contrib
            votes.append(AgentVote(agent=agent, bias=o.bias, confidence=o.confidence, weight=round(w, 4), contribution=round(contrib, 4)))

        net = max(-1.0, min(1.0, net))
        net_sign = 1 if net > 0 else (-1 if net < 0 else 0)
        direction = Bias.BULLISH if net_sign > 0 else (Bias.BEARISH if net_sign < 0 else Bias.NEUTRAL)

        # Weighted agreement & average confidence among *active* voters.
        active = [(a, outputs[a]) for a in SCORING_AGENTS if a in outputs and outputs[a].confidence > 0.05 and outputs[a].bias is not Bias.NEUTRAL]
        agree_w = sum(weights[a] for a, o in active if o.bias.sign == net_sign)
        total_w = sum(weights[a] for a, _ in active)
        agreement = (agree_w / total_w) if total_w else 0.0
        avg_conf = (sum(weights[a] * o.confidence for a, o in active) / total_w) if total_w else 0.0

        quality = max(0.0, min(100.0, 50.0 * abs(net) + 30.0 * agreement + 20.0 * avg_conf))

        # Collect all flags; identify vetoes and count degraded agents.
        all_flags: list[RiskFlag] = list(risk.risk_flags)
        for o in outputs.values():
            all_flags.extend(o.risk_flags)
        vetoes = [f for f in all_flags if f.code in self.veto_codes or (f.severity is Severity.CRITICAL and f.source in (AgentName.NEWS_SENTIMENT, AgentName.RISK_MANAGER))]
        degraded = [a for a in SCORING_AGENTS if a in outputs and outputs[a].error]

        mult = regime.quality_multiplier if regime else 1.0
        required_quality = self.min_quality * mult

        decision, reason = self._gate(
            direction, net, agreement, quality, required_quality, vetoes, degraded, risk
        )

        confidence = round(min(1.0, 0.5 * abs(net) + 0.5 * agreement), 3)

        td = TradingDecision(
            symbol=symbol,
            decision=decision,
            bias=direction if decision is not TradeDecision.NO_TRADE else Bias.NEUTRAL,
            confidence=confidence,
            quality_score=round(quality, 1),
            net_directional_score=round(net, 3),
            agreement=round(agreement, 3),
            votes=votes,
            risk_flags=all_flags,
            sizing=risk.sizing if decision is not TradeDecision.NO_TRADE else None,
            reasoning=reason,
        )
        self.log.info(
            "decision",
            decision=str(decision),
            quality=td.quality_score,
            required=round(required_quality, 1),
            net=td.net_directional_score,
            agreement=td.agreement,
            vetoes=[v.code for v in vetoes],
        )
        return td

    def _gate(self, direction, net, agreement, quality, required_quality, vetoes, degraded, risk) -> tuple[TradeDecision, str]:
        """Return (decision, reasoning). Conservative by construction."""
        narrative = (
            f"Net {net:+.2f}, agreement {agreement:.0%}, quality {quality:.0f}/100 "
            f"(required ≥ {required_quality:.0f})."
        )

        if vetoes:
            codes = ", ".join(sorted({v.code for v in vetoes}))
            return TradeDecision.NO_TRADE, f"NO TRADE — hard veto ({codes}). {narrative}"
        if len(degraded) >= 3:
            return TradeDecision.NO_TRADE, f"NO TRADE — {len(degraded)} agents degraded; insufficient information. {narrative}"
        if not risk.approved:
            return TradeDecision.NO_TRADE, f"NO TRADE — risk gate: {risk.rejection_reason}. {narrative}"
        if direction is Bias.NEUTRAL or abs(net) < self.min_net_score:
            return TradeDecision.NO_TRADE, f"NO TRADE — no directional edge (|net| {abs(net):.2f} < {self.min_net_score}). {narrative}"
        if agreement < self.min_agreement:
            return TradeDecision.NO_TRADE, f"NO TRADE — agents disagree (agreement {agreement:.0%} < {self.min_agreement:.0%}). {narrative}"
        if quality < required_quality:
            return TradeDecision.NO_TRADE, f"NO TRADE — quality below regime-adjusted bar. {narrative}"
        # Direction must match the side the Risk Manager sized.
        if risk.sizing is not None and ((direction is Bias.BULLISH) != (risk.sizing.side.value == "buy")):
            return TradeDecision.NO_TRADE, f"NO TRADE — sizing/direction mismatch (safety). {narrative}"

        side = TradeDecision.BUY if direction is Bias.BULLISH else TradeDecision.SELL
        return side, f"{side.value} — conviction and quality cleared all gates. {narrative}"
