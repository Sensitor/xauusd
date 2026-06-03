"""Agent 4 — News & Sentiment Analyst.

Two responsibilities, deliberately separated by reliability:

1. **Event-risk gating (deterministic, never an LLM).** Around high-impact
   scheduled releases (NFP, CPI, FOMC...) spreads blow out and price gaps. The
   agent computes ``minutes_to_next_high_impact`` and an ``in_blackout_window``
   flag from the economic calendar. This is a hard safety mechanism, so it must be
   reproducible — we never let a language model decide whether it's safe to trade
   into FOMC.

2. **Sentiment read (LLM-assisted).** Headlines from Reuters/Bloomberg/FT/Investing
   are scored for gold-relevant sentiment. With no LLM/key, sentiment defaults to
   neutral while the event gate still functions.

Inputs (populated by the data layer):
  ctx.raw['calendar']  -> list of {title, scheduled_at(ISO), importance, ...}
  ctx.raw['headlines'] -> list of {title, source, published_at, url}
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from goldmind.agents.base import BaseAgent
from goldmind.core.context import MarketContext
from goldmind.core.enums import AgentName, Bias, Severity
from goldmind.core.schemas import AgentOutput, NewsEvent, NewsSentimentOutput
from goldmind.llm import complete_structured, get_chat_model

# No-trade window around CRITICAL (high-impact) events.
BLACKOUT_BEFORE_MIN = 30
BLACKOUT_AFTER_MIN = 15

_SYSTEM = (
    "You score financial news sentiment specifically for GOLD (XAUUSD). Output a "
    "single sentiment in [-1, 1] where +1 is strongly bullish for gold (e.g. "
    "escalating geopolitical risk, dovish Fed, falling real yields) and -1 strongly "
    "bearish (hawkish Fed, strong USD, risk-on). Weight reputable wires (Reuters, "
    "Bloomberg, FT) more than aggregators. If headlines are off-topic or thin, "
    "return ~0 with low confidence."
)


class _SentimentLLM(BaseModel):
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


def _to_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def _importance(value: Any) -> Severity:
    s = str(value).lower()
    if s in {"high", "critical", "3", "red"}:
        return Severity.CRITICAL
    if s in {"medium", "warning", "2", "orange"}:
        return Severity.WARNING
    return Severity.INFO


def _parse_calendar(raw: Any) -> list[NewsEvent]:
    events: list[NewsEvent] = []
    for item in raw or []:
        if isinstance(item, NewsEvent):
            events.append(item)
        elif isinstance(item, dict):
            events.append(
                NewsEvent(
                    title=item.get("title", "event"),
                    source=item.get("source", "calendar"),
                    scheduled_at=_to_dt(item.get("scheduled_at") or item.get("date")),
                    importance=_importance(item.get("importance") or item.get("impact")),
                    is_scheduled=True,
                    url=item.get("url"),
                )
            )
    return events


def _parse_headlines(raw: Any) -> list[NewsEvent]:
    out: list[NewsEvent] = []
    for item in raw or []:
        if isinstance(item, dict):
            out.append(
                NewsEvent(
                    title=item.get("title", ""),
                    source=item.get("source", "news"),
                    published_at=_to_dt(item.get("published_at")),
                    importance=_importance(item.get("importance", "info")),
                    url=item.get("url"),
                )
            )
    return out


class NewsSentimentAgent(BaseAgent):
    name = AgentName.NEWS_SENTIMENT
    output_cls = NewsSentimentOutput

    def analyze(self, ctx: MarketContext) -> AgentOutput:
        now = ctx.as_of if ctx.as_of.tzinfo else ctx.as_of.replace(tzinfo=UTC)
        calendar = _parse_calendar(ctx.raw.get("calendar"))
        headlines = _parse_headlines(ctx.raw.get("headlines"))

        # --- deterministic event gate ---
        minutes_to_next: float | None = None
        in_blackout = False
        for ev in calendar:
            if ev.importance is not Severity.CRITICAL or ev.scheduled_at is None:
                continue
            delta_min = (ev.scheduled_at - now).total_seconds() / 60.0
            if -BLACKOUT_AFTER_MIN <= delta_min <= BLACKOUT_BEFORE_MIN:
                in_blackout = True
            if delta_min >= -BLACKOUT_AFTER_MIN:
                minutes_to_next = delta_min if minutes_to_next is None else min(minutes_to_next, delta_min)

        # --- sentiment read ---
        sentiment, conf, reasoning, model = 0.0, 0.0, "No headlines available; sentiment neutral.", None
        if headlines:
            model_obj = get_chat_model("fast", self.settings)
            if model_obj is not None:
                try:
                    human = "Score gold sentiment from these headlines:\n" + "\n".join(
                        f"- ({h.source}) {h.title}" for h in headlines[:25]
                    )
                    res: _SentimentLLM = complete_structured(model_obj, _SentimentLLM, _SYSTEM, human)
                    sentiment, conf, reasoning, model = res.sentiment_score, res.confidence, res.reasoning, self.settings.fast_model
                except Exception as exc:
                    self.log.warning("news_llm_failed", error=str(exc))
                    reasoning = f"{len(headlines)} headlines present but LLM scoring failed; sentiment treated as neutral."
            else:
                reasoning = f"{len(headlines)} headlines present; no LLM configured, sentiment neutral (event gate still active)."

        risk_level = Severity.INFO
        if in_blackout:
            risk_level = Severity.CRITICAL
        elif minutes_to_next is not None and 0 <= minutes_to_next <= 60:
            risk_level = Severity.WARNING

        bias = Bias.BULLISH if sentiment > 0.25 else (Bias.BEARISH if sentiment < -0.25 else Bias.NEUTRAL)
        out = NewsSentimentOutput(
            agent=self.name,
            bias=bias,
            confidence=round(float(conf), 3),
            reasoning=reasoning + (f" High-impact event in {minutes_to_next:.0f} min." if minutes_to_next is not None and minutes_to_next >= 0 else ""),
            sentiment_score=round(float(sentiment), 3),
            risk_level=risk_level,
            minutes_to_next_high_impact=round(minutes_to_next, 1) if minutes_to_next is not None else None,
            in_blackout_window=in_blackout,
            events=(calendar + headlines)[:30],
            model=model,
        )
        if in_blackout:
            out.add_flag("news_blackout", "Inside the no-trade window around a high-impact event.", Severity.CRITICAL)
        elif risk_level is Severity.WARNING:
            out.add_flag("news_proximity", f"High-impact event within ~{minutes_to_next:.0f} min — elevated event risk.", Severity.WARNING)
        return out
