/**
 * Shared UI token helpers: maps domain enums to Tailwind class strings so the
 * BUY/SELL/NO_TRADE and severity color language is defined in exactly one place.
 */
import type { Bias, Severity, TradeDecisionType } from "./types";

/** Border + background + text classes for a decision/directional badge. */
export function decisionClasses(
  d: TradeDecisionType | "BUY" | "SELL" | "NO_TRADE",
): string {
  switch (d) {
    case "BUY":
      return "text-buy border-buy-border bg-buy-soft";
    case "SELL":
      return "text-sell border-sell-border bg-sell-soft";
    default:
      return "text-notrade border-notrade-border bg-notrade-soft";
  }
}

/** Map a directional bias to the decision color family. */
export function biasToDecision(bias: Bias): TradeDecisionType {
  if (bias === "bullish") return "BUY";
  if (bias === "bearish") return "SELL";
  return "NO_TRADE";
}

export function biasClasses(bias: Bias): string {
  return decisionClasses(biasToDecision(bias));
}

/** Plain text color for a directional bias (no background). */
export function biasTextClass(bias: Bias): string {
  if (bias === "bullish") return "text-buy";
  if (bias === "bearish") return "text-sell";
  return "text-notrade";
}

/** Color for a signed value (PnL, R-multiple, contribution). */
export function signedTextClass(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value) || value === 0) {
    return "text-terminal-muted";
  }
  return value > 0 ? "text-buy" : "text-sell";
}

export function severityClasses(sev: Severity): string {
  switch (sev) {
    case "critical":
      return "text-critical border-sell-border bg-sell-soft";
    case "warning":
      return "text-warning border-notrade-border bg-notrade-soft";
    default:
      return "text-info border-[rgba(59,130,246,0.4)] bg-[rgba(59,130,246,0.12)]";
  }
}

/** Solid bar/fill color for a directional bias (used by confidence bars). */
export function biasFillClass(bias: Bias): string {
  if (bias === "bullish") return "bg-buy";
  if (bias === "bearish") return "bg-sell";
  return "bg-notrade";
}

/** Color ramp for a 0–100 quality score. */
export function qualityTextClass(score: number): string {
  if (score >= 70) return "text-buy";
  if (score >= 50) return "text-notrade";
  return "text-sell";
}
