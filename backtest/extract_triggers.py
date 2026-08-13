"""
Extract historical "trigger" events for the backtest replay.

The real trigger-detection strategy isn't decided yet (see the EA's
ShouldEvaluateSetup() placeholder). Until it is, this resamples the historical
M1 data at a fixed cadence - equivalent to what the placeholder trigger does
live - so the replay harness has something to iterate over. Swap this for a
real strategy-based extraction later without changing replay_harness.py's
interface (it just consumes a list of {timestamp, symbol} events).
"""

import argparse
import json
import os
import sys
from datetime import timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_m1_csv

# Sliding window needs 48h of warm-up data (the H1 tier) before a trigger event
# can be evaluated at all.
WARMUP_HOURS = 48


def extract_trigger_events(m1_df: pd.DataFrame, interval_minutes: int, symbol: str, max_events: int = None) -> list:
    start = m1_df['timestamp'].min() + timedelta(hours=WARMUP_HOURS)
    end = m1_df['timestamp'].max()

    events = []
    t = start
    while t <= end:
        events.append({"timestamp": t.isoformat(), "symbol": symbol})
        if max_events and len(events) >= max_events:
            break
        t += timedelta(minutes=interval_minutes)
    return events


def main():
    parser = argparse.ArgumentParser(description="Extract historical trigger events for backtesting")
    parser.add_argument("--csv", default=os.path.join(os.path.dirname(__file__), "..", "data_seed", "XAUUSD_M1.csv"))
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--interval-minutes", type=int, default=15, help="Trigger cadence, matches AnalysisInterval")
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

    events = extract_trigger_events(df, args.interval_minutes, args.symbol, args.max_events)

    if not events:
        print(f"No trigger events produced - the date range is likely narrower than the "
              f"{WARMUP_HOURS}h warm-up window the sliding window needs. Widen --start-date/--end-date.")
        return

    with open(args.output, 'w') as f:
        json.dump(events, f, indent=2)

    print(f"Wrote {len(events)} trigger events to {args.output}")
    print(f"Date range covered: {events[0]['timestamp']} to {events[-1]['timestamp']}")


if __name__ == "__main__":
    main()
