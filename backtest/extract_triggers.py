"""
Extract historical trigger events for the backtest replay.

Runs the EA's actual mechanical trigger (CheckStrategyTrigger's MA-touch +
confirmation + slope state machine, see trigger_detector.py) over the
historical M1 data, so the replay harness iterates over the exact same setup
logic the EA runs live - not an approximation. Each event carries the real
direction/slope the state machine produced, matching what the EA hands to
Agent 2/3 in BuildSignalPayload().
"""

import argparse
import json
import os
import sys
from datetime import timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_m1_csv
from trigger_detector import detect_triggers

# Sliding window needs 48h of warm-up data (the H1 tier) before a trigger event
# can be evaluated at all.
WARMUP_HOURS = 48


def extract_trigger_events(m1_df: pd.DataFrame, symbol: str, max_events: int = None) -> list:
    start = m1_df['timestamp'].min() + timedelta(hours=WARMUP_HOURS)
    warm_df = m1_df[m1_df['timestamp'] >= start]

    events = []
    for e in detect_triggers(warm_df):
        events.append({
            "timestamp": e["timestamp"].isoformat(),
            "symbol": symbol,
            "direction": e["direction"],
            "slope": e["slope"],
        })
        if max_events and len(events) >= max_events:
            break
    return events


def main():
    parser = argparse.ArgumentParser(description="Extract historical trigger events for backtesting")
    parser.add_argument("--csv", default=os.path.join(os.path.dirname(__file__), "..", "data_seed", "XAUUSD_M1.csv"))
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--max-events", type=int, default=200)
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD, restrict to data on/after this date")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD, restrict to data on/before this date")
    parser.add_argument("--output", default=os.path.join(os.path.dirname(__file__), "trigger_events.json"))
    args = parser.parse_args()

    print(f"Loading {args.csv} ...")
    df = load_m1_csv(args.csv)

    if args.start_date:
        df = df[df['timestamp'] >= pd.Timestamp(args.start_date)]
    if args.end_date:
        df = df[df['timestamp'] <= pd.Timestamp(args.end_date)]

    if df.empty:
        print("No data in the requested date range.")
        return

    events = extract_trigger_events(df, args.symbol, args.max_events)

    if not events:
        print(f"No trigger events produced - either the date range is narrower than the "
              f"{WARMUP_HOURS}h warm-up window the sliding window needs, or the MA-touch/"
              f"confirmation/slope setup just didn't fire in this range. Widen --start-date/"
              f"--end-date and try again.")
        return

    with open(args.output, 'w') as f:
        json.dump(events, f, indent=2)

    print(f"Wrote {len(events)} trigger events to {args.output}")
    print(f"Date range covered: {events[0]['timestamp']} to {events[-1]['timestamp']}")


if __name__ == "__main__":
    main()
