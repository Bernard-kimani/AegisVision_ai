"""
Unit tests for the new M1 (1-minute, 6h) sliding-window tier added on top of
the existing M5/H1 tiers. Pure data-layer tests - no Flask app, no LLM API key
required.
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "gui_server", "server"))

from data.sliding_window import SlidingWindowManager
from data.models import CandleData


def make_candle(symbol, timeframe, minutes_ago, close=2000.0):
    return CandleData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=datetime.now() - timedelta(minutes=minutes_ago),
        open_price=close,
        high_price=close + 1,
        low_price=close - 1,
        close_price=close,
        volume=100,
    )


def test_window_sizes_include_m1():
    manager = SlidingWindowManager()
    assert manager.window_1min_size == 360
    assert manager.window_5min_size == 288
    assert manager.window_1hour_size == 48


def test_bulk_load_populates_all_three_tiers():
    manager = SlidingWindowManager()
    window_key = manager.create_connection("XAUUSD", "test")

    candles_1min = [make_candle("XAUUSD", "M1", i) for i in range(400, 0, -1)]  # more than window size
    candles_5min = [make_candle("XAUUSD", "M5", i * 5) for i in range(300, 0, -1)]
    candles_1hour = [make_candle("XAUUSD", "H1", i * 60) for i in range(50, 0, -1)]

    success = manager.bulk_load_data(window_key, candles_5min, candles_1hour, candles_1min)
    assert success is True

    status = manager.get_window_status(window_key)
    assert status["candles_1min_count"] == 360  # trimmed to window size
    assert status["candles_5min_count"] == 288
    assert status["candles_1hour_count"] == 48
    assert status["ready_for_analysis"] is True


def test_insufficient_data_not_ready():
    manager = SlidingWindowManager()
    window_key = manager.create_connection("XAUUSD", "test2")

    candles_1min = [make_candle("XAUUSD", "M1", i) for i in range(5, 0, -1)]
    candles_5min = [make_candle("XAUUSD", "M5", i * 5) for i in range(5, 0, -1)]
    candles_1hour = [make_candle("XAUUSD", "H1", i * 60) for i in range(2, 0, -1)]

    manager.bulk_load_data(window_key, candles_5min, candles_1hour, candles_1min)
    status = manager.get_window_status(window_key)
    assert status["ready_for_analysis"] is False
    assert status["sufficient_data_1min"] is False


def test_add_candle_m1_tier_idempotent_and_trims():
    manager = SlidingWindowManager()
    window_key = manager.create_connection("XAUUSD", "test3")

    ts = datetime.now()
    candle = CandleData(
        symbol="XAUUSD", timeframe="M1", timestamp=ts,
        open_price=2000, high_price=2001, low_price=1999, close_price=2000.5, volume=10,
    )
    manager.add_candle(window_key, candle, "M1")
    manager.add_candle(window_key, candle, "M1")  # same timestamp -> should update, not duplicate

    window_data = manager.get_window_data(window_key)
    assert len(window_data.candles_1min) == 1

    # Fill past the window size and confirm it trims to window_1min_size
    for i in range(400):
        c = make_candle("XAUUSD", "M1", 400 - i)
        manager.add_candle(window_key, c, "M1")

    window_data = manager.get_window_data(window_key)
    assert len(window_data.candles_1min) <= manager.window_1min_size


if __name__ == "__main__":
    test_window_sizes_include_m1()
    test_bulk_load_populates_all_three_tiers()
    test_insufficient_data_not_ready()
    test_add_candle_m1_tier_idempotent_and_trims()
    print("All M1 sliding-window tests passed.")
