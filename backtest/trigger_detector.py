"""
Python port of the EA's real mechanical trigger and standalone SL/TP calc, so
the backtest replays the exact same setup logic the EA runs live instead of
approximating it. Ports three functions 1:1 from ea/AegisVision_EA.mq5:

  - detect_triggers()      <- CheckStrategyTrigger() + GetSlopeToNow() (lines 226-362)
  - compute_ea_stop_loss() <- ComputeStandaloneStopLoss()              (lines 1300-1324)
  - compute_ea_take_profit() <- ComputeStandaloneTakeProfit() + FindNearestSwingTarget()/
                                 FindSwingOnTimeframe()                (lines 1331-1427)

All default parameter values mirror the EA's current compiled `input` values
(MA_Period=20/MODE_SMA, SlopeLookbackBars=15, MinSlopePoints=30, etc.) - if
those EA inputs are ever retuned, these defaults need to move with them, same
"must match the EA" convention used elsewhere in this codebase.

point_size defaults to 0.001, NOT the live EA's assumed 0.01 (2-digit quote,
see the old ingestor.py SL_BUFFER_PRICE comment) - the seed CSV
(data_seed/XAUUSD_M1.csv) is quoted to 3 decimal places (confirmed
empirically: every close price is an exact multiple of 0.001), so that's
this specific historical dataset's actual tick size. MinSlopePoints/
SL_BufferPoints are raw "points" whose real dollar magnitude depends
entirely on this value - if the live broker's actual quote precision
differs, a backtest run isn't directly dollar-comparable to live without
re-checking this.
"""

from typing import Dict, List, Optional

import numpy as np
import pandas as pd


def detect_triggers(
    m1_df: pd.DataFrame,
    ma_period: int = 20,
    slope_lookback_bars: int = 15,
    min_slope_points: float = 30.0,
    point_size: float = 0.001,
    max_confirmation_bars: int = 2,
    min_body_percent_of_range: float = 40.0,
) -> List[Dict]:
    """Sequential bar-by-bar scan mirroring CheckStrategyTrigger()'s state
    machine exactly: touch-side context -> first-confirmation (body%/color/
    close-side) within max_confirmation_bars -> slope gate. Must stay
    sequential (not vectorized) - the confirmation window is genuine state
    carried bar-to-bar, same as the EA's pendingTouch/pendingDirection/
    pendingBarsWaited globals."""
    df = m1_df.reset_index(drop=True)
    ma = df["close"].rolling(ma_period).mean().to_numpy()
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    timestamps = df["timestamp"].tolist()

    def slope_to_now(idx: int, direction: str) -> float:
        if idx < slope_lookback_bars or np.isnan(ma[idx - slope_lookback_bars]):
            return 0.0
        window = ma[idx - slope_lookback_bars: idx + 1][::-1]  # window[0] = now, window[k] = k bars back
        extreme_idx = int(np.argmin(window[1:])) + 1 if direction == "BUY" else int(np.argmax(window[1:])) + 1
        if extreme_idx <= 0:
            return 0.0
        return (window[0] - window[extreme_idx]) / extreme_idx / point_size

    events: List[Dict] = []
    pending_touch = False
    pending_direction: Optional[str] = None
    pending_bars_waited = 0

    for idx in range(len(df)):
        if np.isnan(ma[idx]):
            continue
        ma_value = ma[idx]
        body_size = abs(closes[idx] - opens[idx])
        range_size = highs[idx] - lows[idx]
        strong_body = range_size > 0 and (body_size / range_size * 100.0) >= min_body_percent_of_range
        is_bullish = closes[idx] > opens[idx]
        is_bearish = closes[idx] < opens[idx]

        if pending_touch:
            pending_bars_waited += 1
            first_confirm_now = strong_body and (
                (is_bullish and closes[idx] > ma_value) if pending_direction == "BUY"
                else (is_bearish and closes[idx] < ma_value)
            )
            if first_confirm_now:
                slope = slope_to_now(idx, pending_direction)
                direction = pending_direction
                pending_touch = False
                slope_ok = slope >= min_slope_points if direction == "BUY" else slope <= -min_slope_points
                if slope_ok:
                    events.append({"timestamp": timestamps[idx], "direction": direction, "slope": slope})
                continue
            if pending_bars_waited > max_confirmation_bars:
                pending_touch = False  # window expired, no confirming candle appeared
            continue

        # Idle: direction comes only from which side of the MA this candle
        # approached from - no slope involved yet.
        buy_touch = opens[idx] > ma_value and lows[idx] <= ma_value
        sell_touch = opens[idx] < ma_value and highs[idx] >= ma_value
        if not buy_touch and not sell_touch:
            continue
        touch_direction = "BUY" if buy_touch else "SELL"

        first_confirm_now = strong_body and (
            (is_bullish and closes[idx] > ma_value) if touch_direction == "BUY"
            else (is_bearish and closes[idx] < ma_value)
        )
        if first_confirm_now:
            # Touch and first confirmation landed on the same bar.
            slope = slope_to_now(idx, touch_direction)
            slope_ok = slope >= min_slope_points if touch_direction == "BUY" else slope <= -min_slope_points
            if slope_ok:
                events.append({"timestamp": timestamps[idx], "direction": touch_direction, "slope": slope})
            continue

        pending_touch = True
        pending_direction = touch_direction
        pending_bars_waited = 0

    return events


def compute_ea_stop_loss(
    m1_recent: pd.DataFrame, direction: str, lookback_bars: int = 3, buffer_points: float = 100.0, point_size: float = 0.001,
) -> float:
    """Swing high/low of the last lookback_bars closed M1 candles, plus a
    fixed points buffer beyond it - mirrors ComputeStandaloneStopLoss()."""
    recent = m1_recent.tail(lookback_bars)
    buffer = buffer_points * point_size
    if direction == "BUY":
        return float(recent["low"].min() - buffer)
    return float(recent["high"].max() + buffer)


def _find_swing_on_timeframe(
    df: pd.DataFrame, direction: str, swing_lookback_bars: int, swing_exclude_recent_bars: int,
) -> Optional[float]:
    if swing_exclude_recent_bars > 0:
        window = df.iloc[-(swing_exclude_recent_bars + swing_lookback_bars):-swing_exclude_recent_bars]
    else:
        window = df.tail(swing_lookback_bars)
    if window.empty:
        return None
    return float(window["high"].max()) if direction == "BUY" else float(window["low"].min())


def _find_nearest_swing_target(
    direction: str, price: float, m5_df: pd.DataFrame, h1_df: pd.DataFrame,
    swing_lookback_bars: int, swing_exclude_recent_bars: int,
) -> Optional[float]:
    target_5m = _find_swing_on_timeframe(m5_df, direction, swing_lookback_bars, swing_exclude_recent_bars)
    target_1h = _find_swing_on_timeframe(h1_df, direction, swing_lookback_bars, swing_exclude_recent_bars)
    candidates = [
        t for t in (target_5m, target_1h)
        if t is not None and ((direction == "BUY" and t > price) or (direction == "SELL" and t < price))
    ]
    if not candidates:
        return None
    return min(candidates) if direction == "BUY" else max(candidates)


def compute_ea_take_profit(
    direction: str,
    entry_price: float,
    sl: float,
    m5_recent: pd.DataFrame,
    h1_recent: pd.DataFrame,
    mode: str = "TP_NEAREST_SWING",
    swing_lookback_bars: int = 50,
    swing_exclude_recent_bars: int = 3,
    fixed_rr_multiple: float = 2.0,
) -> float:
    """Nearest 5m/1h swing high/low beyond entry (TP_NEAREST_SWING, the EA's
    default), falling back to a fixed R:R multiple of the stop distance
    (TP_FIXED_RR, or when no swing target is found) - mirrors
    ComputeStandaloneTakeProfit()/FindNearestSwingTarget()."""
    if mode == "TP_NEAREST_SWING":
        swing_target = _find_nearest_swing_target(
            direction, entry_price, m5_recent, h1_recent, swing_lookback_bars, swing_exclude_recent_bars,
        )
        if swing_target is not None:
            return swing_target

    risk_dist = abs(entry_price - sl)
    return entry_price + risk_dist * fixed_rr_multiple if direction == "BUY" else entry_price - risk_dist * fixed_rr_multiple
