"""Agent 9 — Execution Engine.

Turns an approved ``TradingDecision`` into broker actions and manages the open
position (break-even, trailing, partial take-profits). It is deliberately decoupled
from any specific broker via the :class:`Broker` protocol, so the same engine drives
a live MT5 account, a :class:`PaperBroker` (shadow mode / dev), or the backtester.

Safety: the engine honors ``execution_mode``. In ``shadow`` it never sends an order
— it records what it *would* have done. ``semi_auto`` requires an explicit
``approved=True`` (a human/API gate) before routing. Only ``full_auto`` routes
straight through.
"""

from __future__ import annotations

import itertools
from time import perf_counter
from typing import Protocol, runtime_checkable

from goldmind.config import Settings, get_settings
from goldmind.core.enums import ExecutionMode, OrderType, TradeDecision
from goldmind.core.schemas import (
    OpenPosition,
    OrderRequest,
    OrderResult,
    PositionSizing,
    TradingDecision,
)
from goldmind.logging import get_logger


@runtime_checkable
class Broker(Protocol):
    def place_order(self, req: OrderRequest, ref_price: float | None = None) -> OrderResult: ...
    def modify(self, ticket: int, stop_loss: float | None = None, take_profit: float | None = None) -> bool: ...
    def close(self, ticket: int, volume: float | None = None, ref_price: float | None = None) -> OrderResult: ...
    def positions(self) -> list[OpenPosition]: ...


class PaperBroker:
    """In-memory broker for shadow mode, dev, and tests. Fills at the requested/
    reference price with an optional fixed slippage so behavior is deterministic."""

    def __init__(self, slippage_points: float = 0.0) -> None:
        self._tickets = itertools.count(1)
        self._positions: dict[int, OpenPosition] = {}
        self.slippage_points = slippage_points
        self.log = get_logger("broker.paper")

    def place_order(self, req: OrderRequest, ref_price: float | None = None) -> OrderResult:
        price = ref_price if ref_price is not None else (req.price or 0.0)
        fill = price + req.side.sign * self.slippage_points
        ticket = next(self._tickets)
        self._positions[ticket] = OpenPosition(
            ticket=ticket, symbol=req.symbol, side=req.side, volume=req.volume,
            entry=fill, stop_loss=req.stop_loss, take_profit=req.take_profit,
        )
        return OrderResult(accepted=True, broker_order_id=ticket, filled_price=fill,
                           requested_price=price, slippage_points=abs(fill - price), latency_ms=0.0,
                           message="paper fill")

    def modify(self, ticket: int, stop_loss=None, take_profit=None) -> bool:
        pos = self._positions.get(ticket)
        if not pos:
            return False
        if stop_loss is not None:
            pos.stop_loss = stop_loss
        if take_profit is not None:
            pos.take_profit = take_profit
        return True

    def close(self, ticket: int, volume=None, ref_price=None) -> OrderResult:
        pos = self._positions.get(ticket)
        if not pos:
            return OrderResult(accepted=False, message="unknown ticket")
        vol = volume or pos.volume
        if vol >= pos.volume:
            self._positions.pop(ticket, None)
        else:
            pos.volume -= vol
        return OrderResult(accepted=True, broker_order_id=ticket, filled_price=ref_price, message="paper close")

    def positions(self) -> list[OpenPosition]:
        return list(self._positions.values())


class ExecutionEngine:
    def __init__(self, broker: Broker, settings: Settings | None = None) -> None:
        self.broker = broker
        self.settings = settings or get_settings()
        self.log = get_logger("agent.execution")

    # ---- order routing ----
    def execute(self, decision: TradingDecision, ref_price: float | None = None, *, approved: bool = False) -> OrderResult | None:
        if decision.decision is TradeDecision.NO_TRADE or decision.sizing is None:
            self.log.info("execute_skip", reason="no_trade")
            return None

        mode = self.settings.execution_mode
        if mode is ExecutionMode.SHADOW:
            self.log.info("shadow_order", decision=str(decision.decision), lots=decision.sizing.lot_size,
                          entry=decision.sizing.entry, sl=decision.sizing.stop_loss)
            return OrderResult(accepted=False, message="shadow mode — order not sent", requested_price=decision.sizing.entry)
        if mode is ExecutionMode.SEMI_AUTO and not approved:
            self.log.info("awaiting_approval", decision_id=str(decision.id))
            return OrderResult(accepted=False, message="semi_auto — awaiting human approval")

        req = self._build_request(decision)
        t0 = perf_counter()
        result = self.broker.place_order(req, ref_price=ref_price)
        result.latency_ms = round((perf_counter() - t0) * 1000.0, 2)
        if result.slippage_points and result.slippage_points > req.deviation_points:
            self.log.warning("high_slippage", slippage=result.slippage_points, tolerance=req.deviation_points)
        self.log.info("order_routed", accepted=result.accepted, fill=result.filled_price, latency_ms=result.latency_ms)
        return result

    def _build_request(self, decision: TradingDecision) -> OrderRequest:
        s: PositionSizing = decision.sizing  # type: ignore[assignment]
        first_tp = s.take_profits[0].price if s.take_profits else None
        return OrderRequest(
            symbol=s.symbol, side=s.side, order_type=OrderType.MARKET, volume=s.lot_size,
            price=s.entry, stop_loss=s.stop_loss, take_profit=first_tp, decision_id=decision.id,
            comment=f"goldmind:{str(decision.id)[:8]}",
        )

    # ---- trade management ----
    def manage(self, position: OpenPosition, sizing: PositionSizing, current_price: float) -> list[str]:
        """Apply break-even and trailing rules to an open position. Returns the
        list of actions taken (for logging/audit)."""
        actions: list[str] = []
        in_profit = (current_price - position.entry) * position.side.sign

        # Break-even: once price is +break_even distance in our favor, lock entry.
        be_distance = abs(sizing.break_even_price - position.entry) if sizing.break_even_price else None
        sl_below_entry = position.stop_loss is None or position.side.sign * (position.entry - position.stop_loss) > 0
        if be_distance and in_profit >= be_distance and sl_below_entry and self.broker.modify(position.ticket, stop_loss=position.entry):
            actions.append("moved_sl_to_breakeven")

        # Trailing: keep SL at trailing_distance behind price once beyond BE.
        if sizing.trailing_distance and in_profit >= (be_distance or 0):
            new_sl = current_price - position.side.sign * sizing.trailing_distance
            improves = position.stop_loss is None or position.side.sign * (new_sl - position.stop_loss) > 0
            if improves and self.broker.modify(position.ticket, stop_loss=round(new_sl, 3)):
                actions.append(f"trail_sl->{round(new_sl, 3)}")

        if actions:
            self.log.info("position_managed", ticket=position.ticket, actions=actions)
        return actions
