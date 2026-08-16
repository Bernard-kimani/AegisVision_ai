"""
Unit tests for Agent 3 (RiskGuardrail) - the deterministic, non-LLM safety layer.
No network calls, no real LLM - these test the veto logic in isolation.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "gui_server"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "gui_server", "server"))

from agents.guardrail import GuardrailContext, RiskGuardrail
from audit.audit_log import JsonlAuditLogger


def make_guardrail(tmpdir, **overrides):
    audit_store = JsonlAuditLogger(os.path.join(tmpdir, "audit_log.jsonl"))
    kwargs = dict(
        audit_store=audit_store,
        drawdown_state_path=os.path.join(tmpdir, "drawdown_state.json"),
        min_confidence_threshold=70.0,
        min_risk_reward=1.5,
        max_spread=2.0,
        max_daily_drawdown_percent=5.0,
        news_fetcher=None,
    )
    kwargs.update(overrides)
    return RiskGuardrail(**kwargs), audit_store


def base_ctx(**overrides) -> GuardrailContext:
    # ea_stop_loss is the risk leg (Agent 0's real stop); llm_take_profit is
    # the reward leg (Agent 2's own independent target) - risk=10 (2000->1990),
    # reward=20 (2000->2020) => R:R 2.0, comfortably above the 1.5 default.
    defaults = dict(
        symbol="XAUUSD",
        market_snapshot_summary="test summary",
        llm_verdict="ACCEPT",
        llm_confidence=85.0,
        llm_reasoning="looks good",
        proposed_direction="BUY",
        ea_stop_loss=1990.0,
        ea_take_profit=2020.0,
        llm_stop_loss=1985.0,
        llm_take_profit=2020.0,
        current_price=2000.0,
        spread=1.0,
        open_trades_count=0,
        account_equity=None,
    )
    defaults.update(overrides)
    return GuardrailContext(**defaults)


def test_accept_passes_through_when_all_checks_pass():
    with tempfile.TemporaryDirectory() as tmp:
        guardrail, _ = make_guardrail(tmp)
        result = guardrail.evaluate(base_ctx())
        assert result.action == "BUY"
        assert result.vetoed is False
        assert result.stop_loss == 1990.0
        assert result.take_profit == 2020.0


def test_llm_reject_becomes_wait_without_veto_flag():
    with tempfile.TemporaryDirectory() as tmp:
        guardrail, _ = make_guardrail(tmp)
        result = guardrail.evaluate(base_ctx(llm_verdict="REJECT", proposed_direction=None))
        assert result.action == "WAIT"
        assert result.vetoed is False  # nothing to veto - the LLM itself said no


def test_low_confidence_is_vetoed():
    with tempfile.TemporaryDirectory() as tmp:
        guardrail, _ = make_guardrail(tmp, min_confidence_threshold=70.0)
        result = guardrail.evaluate(base_ctx(llm_confidence=50.0))
        assert result.action == "WAIT"
        assert result.vetoed is True
        assert "confidence" in result.veto_reason


def test_poor_risk_reward_is_vetoed():
    with tempfile.TemporaryDirectory() as tmp:
        guardrail, _ = make_guardrail(tmp, min_risk_reward=1.5)
        # risk = 10 (2000->ea_stop_loss 1990), reward = 5 (2000->llm_take_profit
        # 2005) => R:R 0.5, below 1.5. The LLM's own target is what's checked -
        # the EA's stop stays at the base_ctx default.
        result = guardrail.evaluate(base_ctx(llm_take_profit=2005.0))
        assert result.action == "WAIT"
        assert result.vetoed is True
        assert "R:R" in result.veto_reason


def test_missing_llm_target_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        guardrail, _ = make_guardrail(tmp)
        # LLM ACCEPTed but its response didn't parse a usable take-profit -
        # Agent 3 can't validate the R:R comparison, so it must not silently pass.
        result = guardrail.evaluate(base_ctx(llm_take_profit=None))
        assert result.action == "WAIT"
        assert result.vetoed is True
        assert "risk:reward" in result.veto_reason


def test_wide_spread_is_vetoed():
    with tempfile.TemporaryDirectory() as tmp:
        guardrail, _ = make_guardrail(tmp, max_spread=2.0)
        result = guardrail.evaluate(base_ctx(spread=5.0))
        assert result.action == "WAIT"
        assert result.vetoed is True
        assert "spread" in result.veto_reason


def test_daily_drawdown_limit_is_vetoed_and_persists_across_instances():
    with tempfile.TemporaryDirectory() as tmp:
        guardrail1, _ = make_guardrail(tmp, max_daily_drawdown_percent=5.0)
        # Day starts at equity 10000; first call just records the baseline, no drawdown yet
        result1 = guardrail1.evaluate(base_ctx(account_equity=10000.0))
        assert result1.vetoed is False

        # Equity now down 6% intraday - should trip the limit
        result2 = guardrail1.evaluate(base_ctx(account_equity=9400.0))
        assert result2.action == "WAIT"
        assert result2.vetoed is True
        assert "drawdown" in result2.veto_reason

        # A brand-new RiskGuardrail instance (simulating a server restart) must
        # see the same drawdown state from disk, not reset it.
        guardrail2, _ = make_guardrail(tmp, max_daily_drawdown_percent=5.0)
        result3 = guardrail2.evaluate(base_ctx(account_equity=9400.0))
        assert result3.vetoed is True


def test_news_blackout_hard_blocks_regardless_of_confidence():
    class FakeNewsFetcher:
        def get_high_impact_news(self, hours_ahead, hours_behind):
            return [{"time": None, "currency": "USD", "event": "NFP", "impact": "HIGH"}]

        def get_news_impact_on_pair(self, symbol, events, critical_window_minutes=30):
            return "CRITICAL"

    with tempfile.TemporaryDirectory() as tmp:
        guardrail, _ = make_guardrail(tmp, news_fetcher=FakeNewsFetcher())
        result = guardrail.evaluate(base_ctx(llm_confidence=99.0))
        assert result.action == "WAIT"
        assert result.vetoed is True
        assert "news" in result.veto_reason


def test_every_evaluation_writes_an_audit_record_even_when_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        guardrail, audit_store = make_guardrail(tmp)
        guardrail.evaluate(base_ctx())
        guardrail.evaluate(base_ctx(llm_confidence=10.0))  # vetoed

        records = audit_store.read_all()
        assert len(records) == 2
        assert records[0].guardrail_vetoed is False
        assert records[1].guardrail_vetoed is True


if __name__ == "__main__":
    test_accept_passes_through_when_all_checks_pass()
    test_llm_reject_becomes_wait_without_veto_flag()
    test_low_confidence_is_vetoed()
    test_poor_risk_reward_is_vetoed()
    test_missing_llm_target_fails_closed()
    test_wide_spread_is_vetoed()
    test_daily_drawdown_limit_is_vetoed_and_persists_across_instances()
    test_news_blackout_hard_blocks_regardless_of_confidence()
    test_every_evaluation_writes_an_audit_record_even_when_accepted()
    print("All guardrail tests passed.")
