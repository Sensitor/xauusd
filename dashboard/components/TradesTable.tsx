import clsx from "clsx";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import type { Trade, TradeStatus } from "@/lib/types";
import {
  fmtCurrency,
  fmtNumber,
  fmtPrice,
  fmtR,
  fmtTime,
  humanize,
} from "@/lib/format";
import { signedTextClass } from "@/lib/ui";

function SideTag({ side }: { side: Trade["side"] }) {
  const buy = side === "buy";
  const Icon = buy ? ArrowUpRight : ArrowDownRight;
  return (
    <span
      className={clsx(
        "pill",
        buy ? "text-buy border-buy-border bg-buy-soft" : "text-sell border-sell-border bg-sell-soft",
      )}
    >
      <Icon className="h-3 w-3" aria-hidden />
      {buy ? "Buy" : "Sell"}
    </span>
  );
}

const STATUS_CLASSES: Record<TradeStatus, string> = {
  open: "text-buy border-buy-border bg-buy-soft",
  pending: "text-notrade border-notrade-border bg-notrade-soft",
  proposed: "text-info border-[rgba(59,130,246,0.4)] bg-[rgba(59,130,246,0.12)]",
  closed: "text-terminal-muted border-terminal-border-strong bg-terminal-surface-2",
  cancelled: "text-terminal-muted border-terminal-border-strong bg-terminal-surface-2",
  rejected: "text-sell border-sell-border bg-sell-soft",
};

function StatusTag({ status }: { status: TradeStatus }) {
  return (
    <span className={clsx("pill", STATUS_CLASSES[status])}>{humanize(status)}</span>
  );
}

interface TradesTableProps {
  trades: Trade[];
  /** Whether to show exit/close columns (hidden for active-only tables). */
  showClose?: boolean;
  emptyMessage?: string;
  caption?: string;
}

export function TradesTable({
  trades,
  showClose = true,
  emptyMessage = "No trades to display.",
  caption,
}: TradesTableProps) {
  if (!trades || trades.length === 0) {
    return (
      <div className="grid place-items-center px-4 py-10 text-sm text-terminal-muted">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr className="border-b border-terminal-border bg-terminal-surface-2/60">
            <th scope="col" className="table-th">Side</th>
            <th scope="col" className="table-th">Status</th>
            <th scope="col" className="table-th text-right">Volume</th>
            <th scope="col" className="table-th text-right">Entry</th>
            <th scope="col" className="table-th text-right">Stop</th>
            {showClose ? (
              <th scope="col" className="table-th text-right">Exit</th>
            ) : null}
            <th scope="col" className="table-th text-right">PnL</th>
            <th scope="col" className="table-th text-right">R</th>
            <th scope="col" className="table-th text-right">R:R</th>
            <th scope="col" className="table-th text-right">Opened</th>
            {showClose ? (
              <th scope="col" className="table-th text-right">Closed</th>
            ) : null}
          </tr>
        </thead>
        <tbody className="divide-y divide-terminal-border">
          {trades.map((t) => (
            <tr key={t.id} className="transition-colors hover:bg-terminal-surface-2/40">
              <td className="table-td"><SideTag side={t.side} /></td>
              <td className="table-td"><StatusTag status={t.status} /></td>
              <td className="table-td tnum text-right">{fmtNumber(t.volume, 2)}</td>
              <td className="table-td tnum text-right">{fmtPrice(t.entry_price)}</td>
              <td className="table-td tnum text-right text-terminal-muted">
                {fmtPrice(t.stop_loss ?? undefined)}
              </td>
              {showClose ? (
                <td className="table-td tnum text-right text-terminal-muted">
                  {fmtPrice(t.exit_price ?? undefined)}
                </td>
              ) : null}
              <td className={clsx("table-td tnum text-right font-semibold", signedTextClass(t.pnl))}>
                {fmtCurrency(t.pnl ?? undefined, { signed: true })}
              </td>
              <td className={clsx("table-td tnum text-right font-semibold", signedTextClass(t.r_multiple))}>
                {fmtR(t.r_multiple ?? undefined)}
              </td>
              <td className="table-td tnum text-right text-terminal-muted">
                {fmtNumber(t.reward_risk ?? undefined, 2)}
              </td>
              <td className="table-td tnum text-right text-terminal-muted">
                {fmtTime(t.opened_at)}
              </td>
              {showClose ? (
                <td className="table-td tnum text-right text-terminal-muted">
                  {fmtTime(t.closed_at)}
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
