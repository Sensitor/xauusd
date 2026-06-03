"""``goldmind`` command-line interface.

    goldmind evaluate            # run one cycle on synthetic data, print the decision
    goldmind backtest --bars N   # synthetic backtest (delegates to backtest.run)
    goldmind graph               # print the LangGraph as mermaid
    goldmind serve --port 8000   # run the FastAPI control plane
    goldmind version
"""

from __future__ import annotations

import argparse
import sys

from goldmind import __version__
from goldmind.logging import configure_logging


def _cmd_evaluate(args: argparse.Namespace) -> int:
    from goldmind.backtest.synthetic import build_synthetic_context
    from goldmind.graph.workflow import Orchestrator

    ctx = build_synthetic_context(drift=args.drift, volatility=args.volatility, seed=args.seed)
    result = Orchestrator().evaluate(ctx)
    d = result.decision
    print(f"\nDecision: {d.decision.value}  (quality={d.quality_score}/100, net={d.net_directional_score:+.2f}, agreement={d.agreement:.0%})")
    print(f"Reasoning: {d.reasoning}\n")
    print("Agent votes:")
    for v in d.votes:
        print(f"  {v.agent.value:18s} {v.bias.value:8s} conf={v.confidence:.2f} weight={v.weight:.2f} contrib={v.contribution:+.3f}")
    if d.sizing:
        s = d.sizing
        print(f"\nProposed: {s.side.value} {s.lot_size} lots @ {s.entry}  SL {s.stop_loss}  RR {s.reward_risk}  risk {s.risk_pct:.2%}")
    return 0


def _cmd_backtest(args: argparse.Namespace) -> int:
    sys.argv = ["goldmind-backtest", *args.rest]
    from goldmind.backtest.run import main as bt_main

    bt_main()
    return 0


def _cmd_graph(_args: argparse.Namespace) -> int:
    from goldmind.graph.workflow import _print_mermaid

    _print_mermaid()
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("goldmind.api.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="goldmind", description="GoldMind AI — XAUUSD multi-agent trading system")
    sub = parser.add_subparsers(dest="command")

    ev = sub.add_parser("evaluate", help="Run one evaluation cycle on synthetic data")
    ev.add_argument("--drift", type=float, default=0.00012)
    ev.add_argument("--volatility", type=float, default=0.0008)
    ev.add_argument("--seed", type=int, default=11)
    ev.set_defaults(func=_cmd_evaluate)

    bt = sub.add_parser("backtest", help="Run a backtest (passes remaining args through)")
    bt.add_argument("rest", nargs=argparse.REMAINDER)
    bt.set_defaults(func=_cmd_backtest)

    gr = sub.add_parser("graph", help="Print the LangGraph workflow as mermaid")
    gr.set_defaults(func=_cmd_graph)

    sv = sub.add_parser("serve", help="Run the FastAPI control plane")
    sv.add_argument("--host", default="0.0.0.0")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--reload", action="store_true")
    sv.set_defaults(func=_cmd_serve)

    sub.add_parser("version", help="Print version").set_defaults(func=lambda _a: print(__version__) or 0)

    args = parser.parse_args(argv)
    configure_logging("INFO")
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
