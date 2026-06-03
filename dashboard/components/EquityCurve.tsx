"use client";

import { useMemo, useState } from "react";
import clsx from "clsx";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { EquityPoint } from "@/lib/types";
import { fmtCurrency, fmtR, fmtTime } from "@/lib/format";

type Metric = "equity" | "r";

interface EquityCurveProps {
  data: EquityPoint[];
  height?: number;
}

interface TooltipPayloadItem {
  payload: EquityPoint;
}

function ChartTooltip({
  active,
  payload,
  metric,
}: {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  metric: Metric;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0]!.payload;
  return (
    <div className="rounded-lg border border-terminal-border-strong bg-terminal-surface-2 px-3 py-2 text-xs shadow-card">
      <div className="text-terminal-muted">{fmtTime(p.t)}</div>
      <div className="mt-1 tnum font-semibold text-terminal-text">
        {metric === "equity" ? fmtCurrency(p.equity) : fmtR(p.r)}
      </div>
      <div className="tnum text-[11px] text-terminal-muted">
        {metric === "equity" ? fmtR(p.r) : fmtCurrency(p.equity)}
      </div>
    </div>
  );
}

export function EquityCurve({ data, height = 260 }: EquityCurveProps) {
  const [metric, setMetric] = useState<Metric>("equity");

  const { gain, isUp } = useMemo(() => {
    if (data.length < 2) return { gain: 0, isUp: true };
    const first = data[0]!;
    const last = data[data.length - 1]!;
    const g = metric === "equity" ? last.equity - first.equity : last.r - first.r;
    return { gain: g, isUp: g >= 0 };
  }, [data, metric]);

  const stroke = isUp ? "#16c784" : "#ea3943";
  const gradId = `equityGrad-${metric}`;

  if (!data || data.length === 0) {
    return (
      <div
        className="grid place-items-center text-sm text-terminal-muted"
        style={{ height }}
      >
        No equity data available.
      </div>
    );
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="tnum text-sm">
          <span className="text-terminal-muted">Net change </span>
          <span className={clsx("font-semibold", isUp ? "text-buy" : "text-sell")}>
            {metric === "equity"
              ? fmtCurrency(gain, { signed: true })
              : fmtR(gain)}
          </span>
        </div>
        <div className="inline-flex rounded-lg border border-terminal-border bg-terminal-surface-2 p-0.5">
          {(["equity", "r"] as Metric[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMetric(m)}
              aria-pressed={metric === m}
              className={clsx(
                "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                metric === m
                  ? "bg-terminal-accent/20 text-terminal-text"
                  : "text-terminal-muted hover:text-terminal-text",
              )}
            >
              {m === "equity" ? "Equity" : "R-curve"}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#222b3a" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="t"
            tickFormatter={(t: string) => fmtTime(t).split(",")[0] ?? t}
            tick={{ fill: "#7d8aa0", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "#222b3a" }}
            minTickGap={48}
          />
          <YAxis
            dataKey={metric}
            tick={{ fill: "#7d8aa0", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={64}
            tickFormatter={(v: number) =>
              metric === "equity"
                ? `$${Math.round(v / 1000)}k`
                : `${v.toFixed(0)}R`
            }
            domain={["dataMin", "dataMax"]}
          />
          <Tooltip
            content={<ChartTooltip metric={metric} />}
            cursor={{ stroke: "#2f3b4f", strokeDasharray: "3 3" }}
          />
          <Area
            type="monotone"
            dataKey={metric}
            stroke={stroke}
            strokeWidth={2}
            fill={`url(#${gradId})`}
            isAnimationActive={false}
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
