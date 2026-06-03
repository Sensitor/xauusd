/**
 * Pure, locale-stable formatting helpers. All functions are null-safe and
 * return an em-dash placeholder for missing values so the UI never renders
 * "NaN" or "undefined".
 */

const DASH = "—"; // em dash

export function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

/** Fixed-decimal number, e.g. fmtNumber(2.345, 2) -> "2.35". */
export function fmtNumber(value: number | null | undefined, digits = 2): string {
  if (!isNum(value)) return DASH;
  return value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** Price formatted for XAUUSD (2 dp by default). */
export function fmtPrice(value: number | null | undefined, digits = 2): string {
  if (!isNum(value)) return DASH;
  return value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** USD currency with optional explicit sign for PnL. */
export function fmtCurrency(
  value: number | null | undefined,
  opts: { signed?: boolean; digits?: number } = {},
): string {
  if (!isNum(value)) return DASH;
  const { signed = false, digits = 2 } = opts;
  const sign = signed && value > 0 ? "+" : "";
  return (
    sign +
    value.toLocaleString("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })
  );
}

/**
 * Percentage. By default expects a fraction (0.62 -> "62.0%"). Pass
 * `alreadyPercent` when the input is already on a 0–100 scale.
 */
export function fmtPct(
  value: number | null | undefined,
  digits = 1,
  opts: { alreadyPercent?: boolean; signed?: boolean } = {},
): string {
  if (!isNum(value)) return DASH;
  const { alreadyPercent = false, signed = false } = opts;
  const pct = alreadyPercent ? value : value * 100;
  const sign = signed && pct > 0 ? "+" : "";
  return `${sign}${pct.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
}

/** R-multiple, e.g. fmtR(1.83) -> "1.83R", fmtR(-1) -> "-1.00R". */
export function fmtR(value: number | null | undefined, digits = 2): string {
  if (!isNum(value)) return DASH;
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}R`;
}

/** Ratio like profit factor; clamps Infinity to a readable token. */
export function fmtRatio(value: number | null | undefined, digits = 2): string {
  if (!isNum(value)) return DASH;
  if (value === Infinity) return "∞"; // ∞
  return value.toFixed(digits);
}

/** Compact absolute time, e.g. "Jun 03, 14:32". */
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return DASH;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** Relative time, e.g. "in 2h 15m" / "3m ago". */
export function fmtRelative(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return DASH;
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return DASH;
  const diffMs = d - now;
  const future = diffMs >= 0;
  const abs = Math.abs(diffMs);
  const mins = Math.round(abs / 60000);
  if (mins < 1) return "now";
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  const body = h > 0 ? `${h}h ${m}m` : `${m}m`;
  return future ? `in ${body}` : `${body} ago`;
}

/** Title-cases an agent / enum identifier: "market_structure" -> "Market Structure". */
export function humanize(id: string | null | undefined): string {
  if (!id) return DASH;
  return id
    .split("_")
    .map((w) => (w.length ? w[0]!.toUpperCase() + w.slice(1) : w))
    .join(" ");
}

/** Short label for a directional bias. */
export function biasLabel(bias: string | null | undefined): string {
  if (!bias) return DASH;
  return humanize(bias);
}
