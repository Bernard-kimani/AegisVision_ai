"""
Agent 3: Risk & Audit Guardrail Engine (deterministic, non-LLM).

Independent safety layer that can veto a trade regardless of what Agent 2 (the
LLM) decided. Every evaluation - accepted or vetoed - writes one immutable
AuditRecord. Checks run in a fixed order; the first failure wins and forces
WAIT.

The risk:reward check is this agent's centerpiece: the EA (Agent 0) and the
LLM (Agent 2) each independently produce a stop-loss/take-profit read, with
zero visibility into each other's numbers. This is the one place those two
numbers ever meet - risk is the EA's real stop (what will actually be traded),
reward is the LLM's own proposed target (its independent read of how
profitable the setup looks). A confident ACCEPT whose own target doesn't
clear the EA's real risk by the configured minimum still gets vetoed here.

Max-simultaneous-trades is deliberately NOT checked here - the EA gates that
itself (by its own MagicNumber) before it ever sends a signal, so this agent
never sees a request to count. Agent 2 gets the open-position context instead
and makes its own qualitative stacking/correlation call.

Daily drawdown and news-blackout state matter here specifically because they
must survive a GUI/server restart - see drawdown_state.json persistence below.
Without persistence, stopping and restarting the server mid-day would silently
reset the very limit meant to stop you after a bad day.
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from audit.audit_log import AuditRecord, AuditStore

logger = logging.getLogger(__name__)

NEWS_BLACKOUT_IMPACT_LEVELS = ("CRITICAL",)  # news_fetcher.get_news_impact_on_pair() level that forces a hard block


@dataclass
class GuardrailContext:
    symbol: str
    market_snapshot_summary: str
    llm_verdict: str  # ACCEPT | REJECT
    llm_confidence: float
    llm_reasoning: str
    proposed_direction: Optional[str]  # BUY | SELL | None
    ea_stop_loss: Optional[float]  # Agent 0's real stop - what actually gets traded, and the risk leg of the R:R check
    ea_take_profit: Optional[float]  # Agent 0's real target - audit/logging only, never used in the R:R check
    llm_stop_loss: Optional[float] = None  # Agent 2's own independent read - audit/logging only
    llm_take_profit: Optional[float] = None  # Agent 2's own independent read - the reward leg of the R:R check
    current_price: Optional[float] = None
    spread: float = 0.0
    open_trades_count: int = 0
    account_equity: Optional[float] = None
    news_blackout_minutes: Optional[int] = None


@dataclass
class GuardrailResult:
    action: str  # BUY | SELL | WAIT
    vetoed: bool
    veto_reason: Optional[str]
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class RiskGuardrail:
    def __init__(
        self,
        audit_store: AuditStore,
        drawdown_state_path: str,
        min_confidence_threshold: float = 70.0,
        min_risk_reward: float = 1.5,
        max_spread: float = 2.0,
        max_daily_drawdown_percent: float = 5.0,
        default_news_blackout_minutes: int = 30,
        news_fetcher=None,
    ):
        self.audit_store = audit_store
        self.drawdown_state_path = drawdown_state_path
        self.min_confidence_threshold = min_confidence_threshold
        self.min_risk_reward = min_risk_reward
        self.max_spread = max_spread
        self.max_daily_drawdown_percent = max_daily_drawdown_percent
        self.default_news_blackout_minutes = default_news_blackout_minutes
        self.news_fetcher = news_fetcher
        os.makedirs(os.path.dirname(self.drawdown_state_path), exist_ok=True)

    # --- Daily drawdown (persisted to disk, keyed by trading day) ---

    def _load_drawdown_state(self) -> Dict[str, Any]:
        if not os.path.exists(self.drawdown_state_path):
            return {}
        try:
            with open(self.drawdown_state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load drawdown state, treating as fresh day: {e}")
            return {}

    def _save_drawdown_state(self, state: Dict[str, Any]) -> None:
        with open(self.drawdown_state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def _current_daily_drawdown_percent(self, account_equity: Optional[float]) -> float:
        """Update and return today's drawdown (%) from the day's starting equity, using
        the lowest equity seen so far today. Returns 0.0 if equity isn't reported
        (older EA builds, or before the EA sends account_equity) - the check
        degrades to a no-op rather than blocking trades on missing data."""
        if account_equity is None:
            return 0.0

        today = datetime.now().strftime("%Y-%m-%d")
        state = self._load_drawdown_state()

        if state.get("date") != today:
            state = {"date": today, "day_start_equity": account_equity, "min_equity_seen": account_equity}
        else:
            state["min_equity_seen"] = min(state.get("min_equity_seen", account_equity), account_equity)

        self._save_drawdown_state(state)

        day_start = state.get("day_start_equity", account_equity)
        if day_start <= 0:
            return 0.0
        return max(0.0, (day_start - state["min_equity_seen"]) / day_start * 100.0)

    # --- News blackout (hard block, not just prompt context) ---

    def is_news_blackout(self, symbol: str, window_minutes: Optional[int] = None) -> bool:
        if self.news_fetcher is None:
            return False
        minutes = window_minutes if window_minutes is not None else self.default_news_blackout_minutes
        try:
            events = self.news_fetcher.get_high_impact_news(hours_ahead=1, hours_behind=1)
            impact = self.news_fetcher.get_news_impact_on_pair(symbol, events, critical_window_minutes=minutes)
            return impact in NEWS_BLACKOUT_IMPACT_LEVELS
        except Exception as e:
            logger.warning(f"News blackout check failed, defaulting to not-blocked: {e}")
            return False

    # --- Risk:Reward: EA's real stop (risk) vs. the LLM's own independent target (reward) ---

    def _compute_risk_reward(self, ctx: GuardrailContext) -> Optional[float]:
        """None means "can't be evaluated" (missing price/EA stop/LLM target, or a
        malformed stop) - the caller treats that as a fail-closed veto, since this
        check is the whole point of cross-validating Agent 0 against Agent 2."""
        if ctx.current_price is None or ctx.ea_stop_loss is None or ctx.llm_take_profit is None:
            return None
        if ctx.proposed_direction == "BUY":
            risk = ctx.current_price - ctx.ea_stop_loss
            reward = ctx.llm_take_profit - ctx.current_price
        elif ctx.proposed_direction == "SELL":
            risk = ctx.ea_stop_loss - ctx.current_price
            reward = ctx.current_price - ctx.llm_take_profit
        else:
            return None
        if risk <= 0:
            return None  # malformed EA stop
        return reward / risk

    # --- Main entrypoint ---

    def evaluate(self, ctx: GuardrailContext) -> GuardrailResult:
        veto_reason: Optional[str] = None
        risk_reward: Optional[float] = None

        if ctx.llm_verdict != "ACCEPT" or not ctx.proposed_direction:
            veto_reason = None  # not a veto, just nothing to act on
            action = "WAIT"
        else:
            action = ctx.proposed_direction

            if ctx.llm_confidence < self.min_confidence_threshold:
                veto_reason = f"confidence {ctx.llm_confidence:.0f}% below threshold {self.min_confidence_threshold:.0f}%"
            else:
                risk_reward = self._compute_risk_reward(ctx)
                if risk_reward is None:
                    veto_reason = "could not validate risk:reward - missing EA stop or LLM target"
                elif risk_reward < self.min_risk_reward:
                    veto_reason = f"LLM target implies R:R {risk_reward:.2f} vs EA stop, below minimum {self.min_risk_reward:.2f}"
                elif ctx.spread > self.max_spread:
                    veto_reason = f"spread {ctx.spread:.1f} exceeds max {self.max_spread:.1f}"
                elif self.is_news_blackout(ctx.symbol, ctx.news_blackout_minutes):
                    veto_reason = "high-impact news blackout window"
                else:
                    drawdown_pct = self._current_daily_drawdown_percent(ctx.account_equity)
                    if drawdown_pct >= self.max_daily_drawdown_percent:
                        veto_reason = f"daily drawdown {drawdown_pct:.1f}% at/above limit {self.max_daily_drawdown_percent:.1f}%"

            if veto_reason:
                action = "WAIT"

        result = GuardrailResult(
            action=action,
            vetoed=veto_reason is not None,
            veto_reason=veto_reason,
            stop_loss=ctx.ea_stop_loss if action in ("BUY", "SELL") else None,
            take_profit=ctx.ea_take_profit if action in ("BUY", "SELL") else None,
        )

        self.audit_store.append(
            AuditRecord.now(
                symbol=ctx.symbol,
                market_snapshot_summary=ctx.market_snapshot_summary,
                llm_verdict=ctx.llm_verdict,
                llm_confidence=ctx.llm_confidence,
                llm_reasoning=ctx.llm_reasoning,
                guardrail_vetoed=result.vetoed,
                guardrail_veto_reason=result.veto_reason,
                final_action=result.action,
                final_stop_loss=result.stop_loss,
                final_take_profit=result.take_profit,
                entry_price=ctx.current_price,
                ea_stop_loss=ctx.ea_stop_loss,
                ea_take_profit=ctx.ea_take_profit,
                llm_stop_loss=ctx.llm_stop_loss,
                llm_take_profit=ctx.llm_take_profit,
                risk_reward=risk_reward,
            )
        )

        return result
