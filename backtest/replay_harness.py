"""
Backtest replay harness - steps through historical trigger events (see
extract_triggers.py) and runs each one through the REAL pipeline (Ingestor ->
VisionComplianceFilter -> RiskGuardrail, actual Gemini calls, actual guardrail
logic), throttled to respect API rate limits. Computes simulated P&L for a
naive "take every trigger" baseline vs. the AI-filtered result over the same
historical price path, to show whether the AI filter actually helps.

This is NOT the live trading loop - it instantiates its own Ingestor/
VisionComplianceFilter/RiskGuardrail rather than talking to a running Flask
server, so it can be run standalone against historical CSVs.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_GUI_SERVER_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gui_server")
sys.path.insert(0, os.path.abspath(_GUI_SERVER_ROOT))
sys.path.insert(0, os.path.abspath(os.path.join(_GUI_SERVER_ROOT, "server")))

from data_loader import M1SliceIndex, load_m1_csv, resample_ohlc
from metrics import compare_before_after
from trigger_detector import compute_ea_stop_loss, compute_ea_take_profit

from data.models import CandleData
from data.preprocessor import DataPreprocessor
from data.sliding_window import SlidingWindowManager
from agents.ingestor import Ingestor
from agents.vision_compliance import VisionComplianceFilter
from agents.guardrail import GuardrailContext, RiskGuardrail
from audit.audit_log import JsonlAuditLogger
from llm import create_provider
from storage.prompt_store import LocalFilePromptStore
from storage.template_image_store import LocalFileTemplateImageStore
from settings import get_settings

logging.basicConfig(level=logging.WARNING)  # keep replay output readable; agent internals stay quiet
logger = logging.getLogger("replay_harness")

WARMUP_HOURS = 48
M1_WINDOW_SIZE = 360
M5_WINDOW_SIZE = 288
H1_WINDOW_SIZE = 48


def df_to_candles(df: pd.DataFrame, timeframe: str, symbol: str) -> List[CandleData]:
    return [
        CandleData(
            symbol=symbol, timeframe=timeframe, timestamp=row.timestamp,
            open_price=float(row.open), high_price=float(row.high), low_price=float(row.low),
            close_price=float(row.close), volume=int(row.volume) if pd.notna(row.volume) else 0,
        )
        for row in df.itertuples()
    ]


def simulate_trade_outcome(price_path: pd.DataFrame, direction: str, stop_loss: float, take_profit: float):
    for row in price_path.itertuples():
        if direction == "BUY":
            if row.low <= stop_loss:
                return "SL_HIT", stop_loss
            if row.high >= take_profit:
                return "TP_HIT", take_profit
        else:
            if row.high >= stop_loss:
                return "SL_HIT", stop_loss
            if row.low <= take_profit:
                return "TP_HIT", take_profit
    if len(price_path) > 0:
        return "TIMEOUT", float(price_path.iloc[-1].close)
    return "NO_DATA", None


def compute_pnl(direction: str, entry_price: float, exit_price: float) -> float:
    return (exit_price - entry_price) if direction == "BUY" else (entry_price - exit_price)


def build_agents(min_confidence: float, min_risk_reward: float, max_spread: float, audit_log_path: str, drawdown_state_path: str):
    settings = get_settings()
    provider = create_provider("gemini", settings.gemini_api_key, "gemini-2.5-flash")

    window_manager = SlidingWindowManager()
    preprocessor = DataPreprocessor(window_manager)
    ingestor = Ingestor(window_manager, preprocessor)

    prompt_store = LocalFilePromptStore(os.path.join(_GUI_SERVER_ROOT, "storage_data", "prompts"))
    template_store = LocalFileTemplateImageStore(os.path.join(_GUI_SERVER_ROOT, "templates_store"))
    audit_store = JsonlAuditLogger(audit_log_path)

    vision_compliance = VisionComplianceFilter(provider, template_store, prompt_store, max_tokens=800, temperature=0.2)

    # News blackout and daily-drawdown vetoes don't apply meaningfully to a
    # historical replay (no live news feed for 2018 data, no real account
    # equity) - disabled here, not in the live guardrail. No max-trades knob
    # to disable anymore either - that veto was removed from the guardrail
    # entirely (the EA gates trade count itself now), so it's a non-issue.
    guardrail = RiskGuardrail(
        audit_store=audit_store,
        drawdown_state_path=drawdown_state_path,
        min_confidence_threshold=min_confidence,
        min_risk_reward=min_risk_reward,
        max_spread=max_spread,
        max_daily_drawdown_percent=100.0,
        news_fetcher=None,
    )

    return ingestor, vision_compliance, guardrail


def run_replay(
    m1_csv_path: str,
    trigger_events_path: str,
    throttle_seconds: float = 12.0,
    max_events: Optional[int] = None,
    min_confidence: float = 60.0,
    min_risk_reward: float = 1.2,
    max_spread: float = 5.0,
    atr_sl_multiplier: float = 2.0,
    atr_tp_multiplier: float = 3.0,
    output_path: str = "backtest_report.json",
    progress_callback=None,
) -> Dict:
    with open(trigger_events_path) as f:
        events = json.load(f)
    if max_events:
        events = events[:max_events]

    print(f"Loading historical M1 data from {m1_csv_path} ...")
    full_m1 = load_m1_csv(m1_csv_path)
    index = M1SliceIndex(full_m1)

    audit_log_path = os.path.join(os.path.dirname(__file__), "backtest_audit_log.jsonl")
    drawdown_state_path = os.path.join(os.path.dirname(__file__), "backtest_drawdown_state.json")
    for stale in (audit_log_path, drawdown_state_path):
        if os.path.exists(stale):
            os.remove(stale)

    raw_trades: List[Dict] = []
    ai_trades: List[Dict] = []
    skipped = 0

    for i, event in enumerate(events):
        event_time = pd.Timestamp(event["timestamp"])
        symbol = event["symbol"]

        m1_window = index.window_ending_at(event_time, WARMUP_HOURS)
        if len(m1_window) < M1_WINDOW_SIZE:
            skipped += 1
            continue

        m1_recent = m1_window.tail(M1_WINDOW_SIZE)
        m5_recent = resample_ohlc(m1_window, "5min").tail(M5_WINDOW_SIZE)
        h1_recent = resample_ohlc(m1_window, "1h").tail(H1_WINDOW_SIZE)

        if len(m5_recent) < 20 or len(h1_recent) < 5:
            skipped += 1
            continue

        # Fresh agent instances per event: a real live server keeps one window
        # per symbol across time, but a backtest jumps between arbitrary
        # historical timestamps, so each event needs its own clean window.
        ingestor, vision_compliance, guardrail = build_agents(min_confidence, min_risk_reward, max_spread, audit_log_path, drawdown_state_path)

        candles_1min = df_to_candles(m1_recent, "M1", symbol)
        candles_5min = df_to_candles(m5_recent, "M5", symbol)
        candles_1hour = df_to_candles(h1_recent, "H1", symbol)
        ingestor.ingest_bulk(symbol, candles_1min, candles_5min, candles_1hour)

        if not ingestor.is_ready(symbol):
            skipped += 1
            continue

        payload = ingestor.build_dynamic_payload(symbol, open_trades=[], chart_timeframe="M5")
        if payload is None:
            skipped += 1
            continue

        # Direction/slope come from the real mechanical trigger (extract_triggers.py
        # / trigger_detector.detect_triggers), same as the EA's CheckStrategyTrigger
        # - Agent 2 only judges it, never invents one (see vision_compliance.py).
        direction = event["direction"]
        entry_price = float(m1_recent.iloc[-1].close)

        # This event's EA-equivalent SL/TP, computed the same way BuildSignalPayload()
        # does live right before sending a signal - the risk leg for Agent 3's R:R
        # check, and (if the trade goes through) what's actually "executed" below.
        ea_sl = compute_ea_stop_loss(m1_recent, direction)
        ea_tp = compute_ea_take_profit(direction, entry_price, ea_sl, m5_recent, h1_recent)

        verdict = vision_compliance.evaluate(
            payload.market_summary_text, payload.chart_image_b64, direction=direction, open_trades=[],
        )

        atr_estimate = float((m1_recent["high"] - m1_recent["low"]).tail(20).mean()) or 0.5
        future_path = index.path_after(event_time, max_rows=500)

        # --- RAW baseline: take every real trigger, unfiltered, fixed ATR-based
        # SL/TP. This is the "before AI filtering" comparison point, not a real
        # strategy - deliberately not the EA's own SL/TP calc above.
        if direction == "BUY":
            raw_sl = entry_price - atr_estimate * atr_sl_multiplier
            raw_tp = entry_price + atr_estimate * atr_tp_multiplier
        else:
            raw_sl = entry_price + atr_estimate * atr_sl_multiplier
            raw_tp = entry_price - atr_estimate * atr_tp_multiplier

        raw_outcome, raw_exit = simulate_trade_outcome(future_path, direction, raw_sl, raw_tp)
        if raw_exit is not None:
            raw_trades.append({
                "timestamp": event["timestamp"], "direction": direction,
                "entry": entry_price, "exit": raw_exit, "outcome": raw_outcome,
                "pnl": compute_pnl(direction, entry_price, raw_exit),
            })

        # --- AI-filtered: only trade if the guardrail actually approves. The EA's
        # stop is the risk leg; the LLM's own independent target (if it accepted)
        # is the reward leg - neither side has seen the other's number, same as live.
        ctx = GuardrailContext(
            symbol=symbol, market_snapshot_summary=payload.market_summary_text[:2000],
            llm_verdict=verdict.verdict, llm_confidence=verdict.confidence, llm_reasoning=verdict.reasoning,
            proposed_direction=direction, ea_stop_loss=ea_sl, ea_take_profit=ea_tp,
            llm_stop_loss=verdict.stop_loss, llm_take_profit=verdict.take_profit,
            current_price=entry_price, spread=0.0, open_trades_count=0, account_equity=None,
        )
        result = guardrail.evaluate(ctx)

        if result.action in ("BUY", "SELL"):
            ai_outcome, ai_exit = simulate_trade_outcome(future_path, result.action, result.stop_loss, result.take_profit)
            if ai_exit is not None:
                ai_trades.append({
                    "timestamp": event["timestamp"], "direction": result.action,
                    "entry": entry_price, "exit": ai_exit, "outcome": ai_outcome,
                    "pnl": compute_pnl(result.action, entry_price, ai_exit),
                })

        msg = f"[{i + 1}/{len(events)}] {event['timestamp']} verdict={verdict.verdict} conf={verdict.confidence:.0f} guardrail={result.action}"
        print(msg)
        if progress_callback:
            progress_callback(i + 1, len(events), msg)

        if i < len(events) - 1:
            time.sleep(throttle_seconds)

    print(f"Done. {len(events) - skipped}/{len(events)} events evaluated ({skipped} skipped - insufficient warmup data).")

    report = compare_before_after(raw_trades, ai_trades)
    report["generated_at"] = datetime.now().isoformat()
    report["events_total"] = len(events)
    report["events_skipped"] = skipped

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"Report written to {output_path}")

    return report


def main():
    parser = argparse.ArgumentParser(description="Replay historical trigger events through the real AegisVision pipeline")
    parser.add_argument("--m1-csv", default=os.path.join(os.path.dirname(__file__), "..", "data_seed", "XAUUSD_M1.csv"))
    parser.add_argument("--events", default=os.path.join(os.path.dirname(__file__), "trigger_events.json"))
    parser.add_argument("--throttle-seconds", type=float, default=12.0)
    parser.add_argument("--max-events", type=int, default=None)
    parser.add_argument("--min-confidence", type=float, default=60.0)
    parser.add_argument("--min-risk-reward", type=float, default=1.2)
    parser.add_argument("--max-spread", type=float, default=5.0)
    parser.add_argument("--output", default=os.path.join(os.path.dirname(__file__), "backtest_report.json"))
    args = parser.parse_args()

    run_replay(
        m1_csv_path=args.m1_csv,
        trigger_events_path=args.events,
        throttle_seconds=args.throttle_seconds,
        max_events=args.max_events,
        min_confidence=args.min_confidence,
        min_risk_reward=args.min_risk_reward,
        max_spread=args.max_spread,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
