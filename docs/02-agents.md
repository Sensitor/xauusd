# 02 — Agent Specifications

> Part of the [GoldMind AI documentation suite](./README.md). Prev:
> [Architecture](./01-architecture.md) · Next: [Database](./03-database.md).

This document specifies each of the ten agents: its responsibility, inputs,
outputs (including the confidence and risk-flag conventions), method, the
rationale behind that method, and concrete upgrade paths. Class and field names
are taken directly from `src/goldmind/`.

---

## 0. Common contract

Every analytical agent subclasses `BaseAgent` (`agents/base.py`) and implements
one method, `analyze(ctx: MarketContext) -> AgentOutput`. The orchestrator calls
`run()`, never `analyze()` directly; `run()` provides:

- **Latency timing** — sets `latency_ms` on the output.
- **Structured logging** — emits `agent_done` with bias, confidence, latency, flags.
- **Fail-safe degradation** — `DataUnavailableError` → a WARNING-flagged neutral
  output; any other exception → a **CRITICAL** `agent_error` flagged neutral
  output. A degraded agent is "no information", never a confident signal.

All outputs derive from `AgentOutput` (`core/schemas.py`):

| Field | Type | Meaning |
|-------|------|---------|
| `agent` | `AgentName` | Stable identifier (enum). |
| `bias` | `Bias` | `bullish` / `bearish` / `neutral`. `.sign` ∈ {+1, −1, 0}. |
| `confidence` | `float ∈ [0,1]` | Calibrated self-confidence (validated in range). |
| `reasoning` | `str` | Human-readable explanation. |
| `risk_flags` | `list[RiskFlag]` | Structured warnings; CRITICAL ones can veto. |
| `analysis` | `dict` | Agent-specific structured detail. |
| `model` | `str \| None` | Provenance: `"rule_based"`, `"deterministic"`, or a model id. |
| `latency_ms` | `float \| None` | Set by `run()`. |
| `error` | `str \| None` | Set when degraded; consumers treat as low-information. |

The atom of the vote is `signed_confidence = confidence × bias.sign ∈ [-1, 1]`.

A `RiskFlag` carries `code` (machine string), `message`, `severity`
(`info` / `warning` / `critical`), and `source` (the emitting agent). The
Decision Engine and Risk Manager treat CRITICAL flags as hard vetoes regardless
of vote scores.

---

## 1. Market Structure Agent (SMC) — weight 0.25

`agents/market_structure.py` · `MarketStructureAgent` · output
`MarketStructureOutput`

**Responsibility.** Read the price structure the way a Smart-Money-Concepts
trader does, strictly causally (no repainting), across M5/M15/H1/H4, and produce
a structural bias plus the supporting objects.

**Inputs.** OHLCV per timeframe from `ctx`. No external data, no LLM. This is the
most deterministic agent, which is *why* it carries the largest weight.

**Method.**
- **Swings → trend.** `swing_points(high, low, left=2, right=2)`
  (`indicators/technical.py`) marks confirmed fractal highs/lows. A swing
  requires `right` future bars to confirm, so the most recent `right` bars can
  never be swings — this is the explicit anti-repaint guarantee. Trend is
  `bullish` on higher-highs + higher-lows, `bearish` on lower-highs +
  lower-lows, else `neutral`.
- **BOS / CHOCH.** A close beyond the last swing in the trend direction is a
  Break of Structure (continuation); beyond it *against* the trend is a Change
  of Character (early reversal). The per-timeframe directional score leans the
  opposite way on a CHOCH.
- **Fair Value Gaps.** 3-candle imbalances (`low[i] > high[i-2]` bullish,
  `high[i] < low[i-2]` bearish), with a `mitigated` flag computed only from
  subsequent bars.
- **Order Blocks.** Last opposite-color candle before an impulsive (>80% body)
  break.
- **Liquidity pools.** Buyside (above swing highs) / sellside (below swing lows),
  with a `swept` flag.
- **Premium/Discount.** Where price sits within the most recent dealing range
  (0 = deep discount, 1 = deep premium).
- **MTF alignment.** Weighted average of per-timeframe scores with higher
  timeframes weighted more (`H4 0.40, H1 0.30, M15 0.20, M5 0.10`); `agreement`
  is how unanimous the directional timeframes are.

**Output specifics.** `structural_bias`, `timeframe_trends[]`,
`fair_value_gaps[]`, `order_blocks[]`, `liquidity_pools[]`, `premium_discount`,
`mtf_alignment ∈ [-1,1]`. `confidence = min(1, |alignment|·1.1) · (0.5 + 0.5·agreement)`.

**Risk flags.** `htf_choch` (WARNING) when a higher TF changes character;
`buying_in_premium` / `selling_in_discount` (WARNING) for poor trade location.

**Rationale.** Determinism here is the whole point — it is reproducible and
auditable, and it anchors the system in market *behavior* rather than a single
indicator's lag.

**Upgrades.** Treat swing detection's `left/right` as ATR/volatility-adaptive;
add internal-vs-swing liquidity distinction; score FVG/OB *confluence* with the
premium/discount zone instead of reporting them independently; add session-aware
liquidity (Asia range, London/NY highs).

---

## 2. Technical Agent — weight 0.20

`agents/technical.py` · `TechnicalAgent` · output `TechnicalOutput`

**Responsibility.** Distill the classic indicator stack into three explainable
scores.

**Inputs.** OHLCV per timeframe; requires ≥60 bars per timeframe for warm-up.
Deterministic, no LLM.

**Method.** `compute_snapshot()` builds an `IndicatorSnapshot` per timeframe
(RSI-14, MACD 12/26/9, EMA 20/50/200, ATR-14, Bollinger 20/2, relative volume,
ATR%). Each indicator casts an explicit −1/0/+1 vote (`_indicator_votes`); the
per-timeframe score is the mean of active votes; timeframes are blended with
higher-TF weighting. Outputs:
- `bullish_bearish_score ∈ [-1,1]` — weighted directional read.
- `indicator_alignment_score ∈ [0,1]` — fraction of all cast votes agreeing with
  the net sign.
- `momentum_score ∈ [-1,1]` — volatility-scaled MACD histogram plus normalized RSI.

`bias` thresholds at ±0.2; `confidence = min(1, |score|) · (0.4 + 0.6·alignment)`.

**Risk flags.** `elevated_volatility` (WARNING) when H1 ATR% > 1.2%;
`no_technical_edge` (INFO) when |score| < 0.15.

**Rationale.** Per-indicator voting makes the output fully explainable — the
dashboard can show exactly which indicators agreed and which dissented — and
avoids a single indicator dominating.

**Upgrades.** Indicators are correlated, so equal voting double-counts
trend-following signals; group them (trend / momentum / volatility / volume) and
combine groups. Make RSI thresholds regime-dependent (overbought ≠ exit in a
strong trend). Consider divergence detection (price vs. RSI/MACD).

---

## 3. Macro Agent — weight 0.20

`agents/macro.py` · `MacroAgent` · output `MacroOutput`

**Responsibility.** Form a *gold-specific* macro bias from the
rate/inflation/risk complex: CPI, Core CPI, PPI, NFP, Unemployment, FOMC,
Treasury yields, DXY, geopolitics.

**Inputs.** `ctx.raw['macro']` — a dict with optional `digest`, `indicators[]`,
`dxy_trend`, `yields_trend`, `risk_environment`. Populated by the data layer.

**Method — two paths.**
- **LLM path (preferred).** When a reasoning model is configured *and* data
  exists, an instructed senior-macro-strategist prompt synthesizes a structured
  `_MacroLLM` (bias, risk environment, DXY/yields trend, confidence, reasoning).
  The system prompt encodes gold's core relationships (inverse to real yields and
  DXY; dovish/risk-off → bullish) and explicitly forbids inventing data.
- **Rule path (fallback).** Transparent scoring: each release's surprise is
  signed by `_SURPRISE_SIGN` (hot inflation/strong labor → bearish gold; higher
  unemployment → bullish), DXY and yields up subtract from the score, risk-off
  adds. `bias` thresholds at ±0.4; **confidence is capped at 0.8** (below the LLM
  ceiling) to reflect the cruder method.
- **Abstain.** With neither LLM nor any macro data, returns a degraded INFO
  output.

**Output specifics.** `macro_bias`, `risk_environment`, `dxy_trend`,
`yields_trend`, `indicators[]`. Flag: `risk_off` (INFO) — supportive for gold but
raises gap/volatility risk.

**Rationale.** Macro reasoning is genuinely linguistic (it weighs narrative,
surprise, and positioning), so it benefits from an LLM — but a system that
silently does nothing when the key is missing is unacceptable, hence the rule
fallback with a lower confidence ceiling.

**Upgrades.** Pull a real-yields series (e.g. 10y TIPS) directly rather than
inferring from nominal yields + DXY; add CFTC COT positioning; quantify
event-surprise *magnitude* (z-score vs. historical surprise distribution) instead
of just sign.

---

## 4. News & Sentiment Agent — weight 0.10 (and a hard event gate)

`agents/news_sentiment.py` · `NewsSentimentAgent` · output `NewsSentimentOutput`

**Responsibility.** Two jobs, deliberately separated by reliability:

1. **Event-risk gating — deterministic, never an LLM.** Around high-impact
   scheduled releases, spreads blow out and price gaps. The agent computes
   `minutes_to_next_high_impact` and `in_blackout_window` from the calendar.
   The window is **30 minutes before to 15 minutes after** a CRITICAL event
   (`BLACKOUT_BEFORE_MIN = 30`, `BLACKOUT_AFTER_MIN = 15`). This is a safety
   mechanism, so it must be reproducible — a language model never decides
   whether it is safe to trade into FOMC.
2. **Sentiment read — LLM-assisted.** Headlines from Reuters/Bloomberg/FT/
   Investing are scored to a single gold-relevant sentiment in `[-1,1]` using the
   *fast* model. With no LLM/key, sentiment defaults to neutral **while the event
   gate still functions**.

**Inputs.** `ctx.raw['calendar']` (list of scheduled events with importance) and
`ctx.raw['headlines']`.

**Output specifics.** `sentiment_score`, `risk_level` (INFO/WARNING/CRITICAL),
`minutes_to_next_high_impact`, `in_blackout_window`, `events[]`. `bias` thresholds
at ±0.25.

**Risk flags.** `news_blackout` (**CRITICAL** — a Decision-Engine veto code) when
inside the window; `news_proximity` (WARNING) when a high-impact event is within
~60 minutes.

**Rationale.** The single most important line in this agent is that the gate is
deterministic. Sentiment is allowed to be fuzzy because its worst case merely
nudges quality; the gate's worst case is trading into a CPI print, so it is
hard-coded and testable.

**Upgrades.** Source-weight and decay sentiment by recency; deduplicate
headlines; widen the blackout dynamically from the Learning Engine's
news-proximity insight; add a "surprise vs. consensus" reaction model so the
agent can lean directionally *after* a release prints, not just gate before it.

---

## 5. Chart Vision Agent — weight 0.10

`agents/chart_vision.py` · `ChartVisionAgent` · output `ChartVisionOutput`

**Responsibility.** Read a TradingView-style screenshot with a multimodal model:
dominant trend, key horizontal S/R (as numeric prices off the axis), liquidity
zones, and classic patterns (double top/bottom, H&S and inverse, flags,
triangles, breakouts).

**Inputs.** `ctx.screenshot_path` and a configured vision model
(`vision_model`, default GPT-4o-class). Abstains cleanly (INFO-degraded) if
either is missing.

**Method.** `complete_structured()` with an image block → `_VisionLLM`. The
prompt insists on reporting only patterns actually visible (no hallucination) and
a clarity-based confidence.

**Output specifics.** `detected_trend`, `patterns[]` (name, direction,
confidence), `support_levels[]`, `resistance_levels[]`, `risk_areas[]`,
`image_ref`.

**Risk flags.** `bearish_reversal_pattern` (WARNING) for a high-confidence double
top / H&S; `bullish_reversal_pattern` (INFO) for the inverse.

**Rationale.** A corroborating voice (10%) that sees visual context — trendlines,
channels, the *gestalt* — that the numeric agents miss, but which must never
drive a decision alone, hence the low weight and the abstain-by-default posture.

**Upgrades.** Vision price reads are noisy; cross-check returned S/R against the
numeric swing levels and discount mismatches. Pin the chart-rendering pipeline
(fixed timeframe, indicators, theme) so inputs are consistent. Consider an
ensemble of two renderings (e.g. clean + with-EMAs) to stabilize the read.

---

## 6. Market Regime Agent — weight 0.10 (and the quality multiplier)

`agents/market_regime.py` · `MarketRegimeAgent` · output `MarketRegimeOutput`

**Responsibility.** Classify the *environment* so the rest of the system adapts
rather than applying one playbook everywhere, and emit the
`quality_multiplier` that mechanically makes the Decision Engine stricter in
chop.

**Inputs.** OHLCV on the primary timeframe (H1, falling back to M15); requires
≥60 bars. Deterministic, no LLM.

**Method.**
- **Trend regime** — ADX ≥ 25 → trending (up/down by EMA50 vs. EMA200 and
  slope), else `ranging`.
- **Volatility regime** — ATR% percentile rank over the recent ~250 bars:
  ≥0.70 `high`, ≤0.30 `low`, else `normal`.
- **Phase regime** — Bollinger width vs. its trailing median, plus whether it is
  rising → `expansion`, else `compression`.
- **Quality multiplier** (`_policy`): starts at 1.0, ×1.25 in a range, ×0.95 in a
  trend, ×1.10 in compression, ×1.10 in high volatility. >1 demands more
  conviction; <1 is permissive.

**Output specifics.** `trend_regime`, `phase_regime`, `volatility_regime`, `adx`,
`quality_multiplier`, `recommended_behavior`, plus `analysis` with `atr_pct`,
`vol_percentile`, `ema_slope`.

**Risk flags.** `high_volatility_regime` (WARNING — size down/widen stops);
`chop_regime` (WARNING — ranging + compression, low expectancy, prefer no trade).

**Rationale.** This is *how the system "avoids trading during uncertainty"* —
not as a vibe but as a scalar multiplied into the required quality threshold. It
is the cleanest mechanical expression of the whole philosophy.

**Upgrades.** Replace the threshold cascade with an unsupervised regime model
(HMM or k-means on [ADX, ATR%, BB-width, return autocorrelation]) for smoother,
data-driven regimes; learn the multiplier from realized expectancy per regime
rather than hand-setting it (the Learning Engine already breaks performance down
by regime).

---

## 7. Risk Manager — hard gate + sizing, weight 0.05 (feasibility)

`agents/risk_manager.py` · `RiskManager` · output `RiskAssessment`

**Responsibility.** The capital-preservation core. **Not a directional voter** —
a deterministic gate plus a sizing calculator. No LLM ever sizes a position.

Full treatment, including the worked sizing example and every circuit breaker, is
in the [Risk Framework](./06-risk-framework.md). In brief:

- **Circuit breakers** (`circuit_breaker`): daily drawdown (default 2%), total
  drawdown (6%), consecutive losses (3), trades/day (5), concurrent positions
  (1). Any breach → no new risk; a daily-DD breach also sets
  `circuit_breaker_active`.
- **Sizing** (`size`): fixed-fractional risk (0.5% equity) with an ATR-anchored
  stop (`stop_distance = 1.5 × ATR`), lot = `risk$ / (stop_distance × 100)`
  floored to the broker lot step, a partial TP ladder (R = 1.5/2.5/4.0, closing
  0.5/0.3/0.2), break-even at +1R, and an ATR trailing distance.
- **Reward:risk gate**: reject setups whose blended RR < `min_reward_risk`
  (1.8).

**Output specifics.** `approved: bool`, `rejection_reason`, `sizing`
(a `PositionSizing`), `account`, `circuit_breaker_active`. On approval
`confidence = 1.0`; on a breaker it emits a CRITICAL `circuit_breaker` flag (a
Decision-Engine veto code).

**Rationale & upgrades** → [Risk Framework](./06-risk-framework.md).

---

## 8. Decision Engine — aggregator

`agents/decision_engine.py` · `DecisionEngine` · output `TradingDecision`

**Responsibility.** Combine the six voters into one explainable verdict, with
`NO_TRADE` as the default.

**Scoring (verified against the code).**

```
net_directional_score = Σ weightᵢ · (confidenceᵢ · directionᵢ)         ∈ [-1, 1]
agreement             = (Σ weightᵢ for voters aligned with net sign)
                        / (Σ weightᵢ over active voters)                 ∈ [0, 1]
avg_confidence        = weighted mean confidence over active voters
quality_score         = 50·|net| + 30·agreement + 20·avg_confidence     ∈ [0, 100]
```

"Active" voters are those with `confidence > 0.05` and a non-neutral bias. The
six voter weights come from `scoring_weights()` (renormalized to 1.0).

**Gate (a trade requires ALL of):**

1. **No CRITICAL veto.** Veto codes are `news_blackout` and `circuit_breaker`,
   plus any CRITICAL flag sourced from News or the Risk Manager.
2. **Fewer than 3 degraded agents.**
3. **Risk Manager approved** (`risk.approved`).
4. `|net_directional_score| ≥ 0.25` (`min_net_score`) and direction ≠ neutral.
5. `agreement ≥ 0.55` (`min_agreement`).
6. `quality_score ≥ 60 × regime.quality_multiplier` (`min_quality` scaled by
   regime).
7. Direction matches the side the Risk Manager actually sized (a safety
   consistency check).

Otherwise: `NO_TRADE`. The thresholds (`min_quality=60`, `min_net_score=0.25`,
`min_agreement=0.55`) are constructor arguments, so they are tunable per
deployment / by the Learning Engine.

**Output specifics.** `decision` (BUY/SELL/NO_TRADE), `bias`, `confidence`,
`quality_score`, `net_directional_score`, `agreement`, `votes[]` (one `AgentVote`
per voter with its `contribution = weight × signed_confidence`), the union of all
`risk_flags`, `reasoning` (a full narrative of net/agreement/quality vs. the
regime-adjusted bar), and `sizing` (only when a trade).

**Rationale.** Putting the philosophy in *one* place, with explicit, named
thresholds and a recorded reason for every gate, is what makes the system
trustworthy and improvable. Every input vote and every gate outcome is on the
`TradingDecision`, so the dashboard and Learning Engine reconstruct *why*, not
just *what*.

**Upgrades.** See [Architecture §6.1](./01-architecture.md#61-isolated-voters-vs-agent-debate)
— a learned, calibrated aggregator over the per-agent features once enough live
trades exist. Also: a small abstention bonus for high regime uncertainty, and
confidence-weighted (rather than binary) agreement.

---

## 9. Execution Engine — broker actions

`agents/execution.py` · `ExecutionEngine` (+ `PaperBroker`, `Broker` protocol)

**Responsibility.** Turn an approved `TradingDecision` into broker actions and
manage the open position.

**Execution-mode gating** (honors `settings.execution_mode`):
- `shadow` — never sends an order; records what it *would* have done and returns
  an `OrderResult(accepted=False, "shadow mode — order not sent")`.
- `semi_auto` — requires an explicit `approved=True` (a human/API gate) before
  routing; otherwise returns "awaiting human approval".
- `full_auto` — routes straight through.

`NO_TRADE` (or missing sizing) is always a no-op.

**Order routing.** `_build_request()` produces a `MARKET` `OrderRequest` for the
sized side/volume with SL and the first TP, tagged with the decision id; it
tracks latency and flags slippage above the deviation tolerance.

**Trade management.** `manage()` applies break-even (lock entry once price is +1R
in favor) and ATR trailing (keep SL `trailing_distance` behind price once beyond
BE), returning the list of actions for audit. There is exactly one such code path
for live, paper, and backtest.

**Rationale.** Mode gating is the operational expression of "decision-support
first": the default `shadow` mode means installing and running the system places
no orders. The `Broker` protocol keeps the engine venue-agnostic.

**Upgrades.** Execute the *full* TP ladder (the current request carries only the
first TP; multi-TP partial closes are managed but the initial broker order sets
one TP); add limit/stop entry routing for better fills; add a kill-switch that
flattens on a circuit-breaker trip; reconcile broker positions on reconnect.

---

## 10. Learning Engine — post-hoc analysis

`agents/learning.py` · `LearningEngine` · output `PerformanceReport`

**Responsibility.** Close the loop: read the realized trade ledger and produce
(a) honest statistics and (b) *actionable* insights that feed back into filters,
risk config, and decision thresholds. Intentionally model-light — the numbers are
deterministic so they can be trusted.

**Inputs.** `list[ClosedTrade]` (DB-row-shaped: realized `r_multiple`, plus
context — regime, volatility regime, hour, `near_news`, quality/agreement/net).

**Metrics.** Win rate, profit factor, **expectancy in R** (the core unit),
per-trade Sharpe and Sortino, max drawdown in R (and a `%` slot), average win/loss
R. Drawdown-in-R is computed from the cumulative R curve (`_max_drawdown_r`).

**Condition mining.** Groups trades by regime, by session hour, and by
agreement bucket (high ≥0.7 vs. low), reporting the best- and worst-expectancy
conditions (minimum 3 trades per group to count).

**Insights** (each a `LearningInsight` with category, statement, evidence,
confidence), gated by sample size (`MIN_SAMPLES_FOR_INSIGHT = 12`):
- Non-positive overall expectancy → tighten filters / pause live risk.
- A negative-expectancy condition → filter it out.
- Low-agreement trades underperforming → raise `min_agreement`.
- News-proximal trades losing → widen the news blackout.
- Average loss worse than −1.05R → stops too tight / slippage / gaps.
- Edge decay (recent third vs. earlier third) → re-examine regime fit / reoptimize.
- Strongest-edge condition → consider weighting toward it.

**Rationale.** The goal is not a prettier report — it is to find, *with
evidence*, where the system has edge and where it bleeds, and to recommend
concrete config changes. R is the unit throughout because it makes wins and
losses comparable across volatility regimes.

**Upgrades.** Apply multiple-comparisons correction (many condition buckets →
false "edges"); bootstrap confidence intervals on expectancy; close the loop
automatically (propose a config diff / open a PR) rather than only emitting text;
add per-agent attribution (which voters' agreement actually predicts R).

---

## Appendix — weighted-scoring reference table

| Agent | `AgentName` | Weight | Renorm. voter weight | Contributes to `net`? | Role |
|-------|-------------|:------:|:--------------------:|:---------------------:|------|
| Market Structure | `market_structure` | 0.25 | 0.2778 | yes | voter |
| Technical | `technical` | 0.20 | 0.2222 | yes | voter |
| Macro | `macro` | 0.20 | 0.2222 | yes | voter |
| News & Sentiment | `news_sentiment` | 0.10 | 0.1111 | yes (+ veto gate) | voter |
| Chart Vision | `chart_vision` | 0.10 | 0.1111 | yes | voter |
| Market Regime | `market_regime` | 0.10 | 0.1111 | yes (+ quality mult.) | voter |
| Risk Manager | `risk_manager` | 0.05 | — | no (hard gate) | gate |

Renormalized voter weights are the six raw weights divided by their sum (0.90),
as computed by `DecisionWeights.scoring_weights()`. The Risk Manager's 0.05 is
the configured feasibility weight; it does not enter `net_directional_score` in
the current engine (see
[Architecture §6.3](./01-architecture.md#63-risk-manager-as-a-gate-not-a-vote)).

Next: [Database](./03-database.md).
