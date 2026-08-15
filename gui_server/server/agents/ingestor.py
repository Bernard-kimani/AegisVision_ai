"""
Agent 1: Data Ingestor & Preprocessor.

Owns the sliding-window buffers and turns them into what Agent 2 needs: a text
market summary plus a fast-rendered chart image. This wraps the existing
SlidingWindowManager/DataPreprocessor/chart_generator - it doesn't reimplement
them, it just gives the rest of the pipeline one narrow interface to depend on.

Also computes deterministic structural context (headroom to the nearest
liquidity pool, higher-timeframe bias) that feeds the Agent 2 vision prompt.
Plain arithmetic over the buffered candles, not an LLM call. Stop-loss/
take-profit are NOT computed here anymore - Agent 0 (the EA) sends its own
fixed-ratio SL/TP, and Agent 2 proposes its own independent SL/TP from the
chart; Agent 3 is where those two numbers get compared. This module's
headroom/bias output is independent structural context, not tied to either
of those specific numbers.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from data.models import CandleData
from data.preprocessor import DataPreprocessor
from data.sliding_window import SlidingWindowManager
from utils.chart_generator import generate_candle_chart

logger = logging.getLogger(__name__)

# Chart is rendered from the M1 tier by default: the strategy's trigger and
# the 20 SMA line it trades against both live on the 1-minute chart, so that's
# the "Image C" the vision-compliance agent needs to see. Swappable per-call.
CHART_TIMEFRAME_INTERVAL_MINUTES = {"M1": 1, "M5": 5, "H1": 60}
TIMEFRAME_TO_WINDOW_ATTR = {"M1": "candles_1min", "M5": "candles_5min", "H1": "candles_1hour"}

STRATEGY_MA_PERIOD = 20  # must match the EA's MA_Period input (MA_Method = MODE_SMA)
STRATEGY_RSI_PERIOD = 14  # standard RSI reading, shown as a sub-panel on M1 charts
SWING_LOOKBACK_CANDLES = 50
SWING_EXCLUDE_RECENT = 3  # ignore the last few candles when looking for a swing level - too close to be a real target


@dataclass
class IngestorPayload:
    symbol: str
    market_summary_text: str
    chart_image_b64: Optional[str]
    chart_timeframe: str
    open_trades: List[Dict[str, Any]]


@dataclass
class TriggerMetrics:
    """Deterministic (non-LLM) structural context for a signal event, matching
    the placeholders in Agent 2's production prompt template. No SL/TP here -
    see the module docstring."""
    direction: str  # BUY | SELL
    headroom_pips: Optional[float]
    higher_timeframe_bias: str


class Ingestor:
    def __init__(self, window_manager: SlidingWindowManager, preprocessor: DataPreprocessor):
        self.window_manager = window_manager
        self.preprocessor = preprocessor

    @staticmethod
    def window_key_for(symbol: str) -> str:
        return f"{symbol}_default"

    def ingest_bulk(
        self,
        symbol: str,
        candles_1min: List[CandleData],
        candles_5min: List[CandleData],
        candles_1hour: List[CandleData],
    ) -> Dict[str, Any]:
        window_key = self.window_key_for(symbol)
        success = self.window_manager.bulk_load_data(window_key, candles_5min, candles_1hour, candles_1min)
        return {"success": success, "status": self.window_manager.get_window_status(window_key)}

    def ingest_single(self, symbol: str, candles_with_timeframe: List[tuple]) -> Dict[str, Any]:
        """candles_with_timeframe: list of (CandleData, timeframe_str) tuples, one per tier per cycle."""
        window_key = self.window_key_for(symbol)
        added_any = False
        for candle, timeframe in candles_with_timeframe:
            if self.window_manager.add_candle(window_key, candle, timeframe):
                added_any = True
        return {"success": added_any, "status": self.window_manager.get_window_status(window_key)}

    def is_ready(self, symbol: str) -> bool:
        return self.window_manager.is_ready_for_analysis(self.window_key_for(symbol))

    def get_window_status(self, symbol: str) -> Dict[str, Any]:
        return self.window_manager.get_window_status(self.window_key_for(symbol))

    def build_dynamic_payload(
        self, symbol: str, open_trades: Optional[List[Dict[str, Any]]] = None, chart_timeframe: str = "M1"
    ) -> Optional[IngestorPayload]:
        window_key = self.window_key_for(symbol)

        t0 = time.perf_counter()
        summary = self.preprocessor.generate_market_summary(window_key)
        if not summary:
            logger.warning(f"Could not generate market summary for {window_key}")
            return None

        market_summary_text = self.preprocessor.format_for_llm(summary)
        preprocess_ms = (time.perf_counter() - t0) * 1000

        t1 = time.perf_counter()
        chart_b64 = None
        try:
            window_data = self.window_manager.get_window_data(window_key)
            attr = TIMEFRAME_TO_WINDOW_ATTR.get(chart_timeframe, "candles_5min")
            candles = getattr(window_data, attr, None) if window_data else None
            if candles:
                # M1 charts show the most recent 240 candles - less than the
                # full 6h/360-candle window so each candle stays visually
                # readable rather than squeezed thin; other timeframes keep
                # the previous 180-candle cap.
                chart_candle_cap = 240 if chart_timeframe == "M1" else 180
                recent = candles[-chart_candle_cap:] if len(candles) > chart_candle_cap else candles
                interval = CHART_TIMEFRAME_INTERVAL_MINUTES.get(chart_timeframe, 5)
                mav = STRATEGY_MA_PERIOD if chart_timeframe == "M1" else None
                rsi_period = STRATEGY_RSI_PERIOD if chart_timeframe == "M1" else None
                chart_b64 = generate_candle_chart(
                    recent, title=f"{symbol} {chart_timeframe}", interval_minutes=interval,
                    mav=mav, rsi_period=rsi_period,
                )
        except Exception as e:
            logger.error(f"Failed to generate chart image for {window_key}: {e}")
        chart_ms = (time.perf_counter() - t1) * 1000

        logger.info(f"timing symbol={symbol} preprocess_ms={preprocess_ms:.0f} chart_ms={chart_ms:.0f}")

        return IngestorPayload(
            symbol=symbol,
            market_summary_text=market_summary_text,
            chart_image_b64=chart_b64,
            chart_timeframe=chart_timeframe,
            open_trades=open_trades or [],
        )

    # --- Deterministic structural context (headroom/higher-tf bias) ---

    def compute_trigger_metrics(self, symbol: str, direction: str) -> Optional[TriggerMetrics]:
        window_data = self.window_manager.get_window_data(self.window_key_for(symbol))
        if not window_data or not window_data.candles_1min:
            return None

        m1 = window_data.candles_1min
        m5 = window_data.candles_5min
        h1 = window_data.candles_1hour
        current_price = m1[-1].close_price

        # Headroom is distance to the nearest 5m/1h swing high/low beyond
        # current price - independent structural context ("how much clear
        # space is there to run"), not tied to anyone's specific SL/TP.
        target_5m = self._find_swing_target(m5, direction)
        target_1h = self._find_swing_target(h1, direction)
        candidates = [t for t in (target_5m, target_1h) if t is not None]
        if direction == "BUY":
            candidates = [t for t in candidates if t > current_price]
            nearest_target = min(candidates) if candidates else None
        else:
            candidates = [t for t in candidates if t < current_price]
            nearest_target = max(candidates) if candidates else None

        headroom_pips = abs(nearest_target - current_price) if nearest_target is not None else None

        bias = self._compute_higher_timeframe_bias(h1, m5)

        return TriggerMetrics(
            direction=direction,
            headroom_pips=headroom_pips,
            higher_timeframe_bias=bias,
        )

    @staticmethod
    def _find_swing_target(candles: List[CandleData], direction: str) -> Optional[float]:
        """Nearest liquidity pool candidate: the highest high (BUY) / lowest low
        (SELL) over a lookback window, excluding the most recent few candles
        (too close to price right now to be a meaningful target)."""
        if not candles or len(candles) < SWING_EXCLUDE_RECENT + 5:
            return None
        window = candles[-SWING_LOOKBACK_CANDLES:] if len(candles) > SWING_LOOKBACK_CANDLES else candles
        relevant = window[: -SWING_EXCLUDE_RECENT] if len(window) > SWING_EXCLUDE_RECENT else window
        if not relevant:
            return None
        if direction == "BUY":
            return max(c.high_price for c in relevant)
        return min(c.low_price for c in relevant)

    @staticmethod
    def _compute_higher_timeframe_bias(h1: List[CandleData], m5: List[CandleData]) -> str:
        parts = []
        # Adapt the EMA period to whatever the H1 buffer actually holds (it's
        # capped at 48 candles / 48 hours - a fixed EMA50 would never have
        # enough bars and this bias line would silently never fire).
        ema_period = min(50, len(h1) - 1) if h1 else 0
        if ema_period >= 10:
            closes = [c.close_price for c in h1]
            k = 2 / (ema_period + 1)
            ema = sum(closes[:ema_period]) / ema_period
            for v in closes[ema_period:]:
                ema = v * k + ema * (1 - k)
            parts.append(
                f"1H price above {ema_period}EMA (bullish bias)" if closes[-1] > ema
                else f"1H price below {ema_period}EMA (bearish bias)"
            )

        if m5 and len(m5) >= 11:
            recent = m5[-10:]
            highs = [c.high_price for c in recent]
            lows = [c.low_price for c in recent]
            if highs[-1] >= max(highs[:-1]) and lows[-1] >= min(lows[:-1]):
                parts.append("5M structure: Higher-Highs/Higher-Lows")
            elif highs[-1] <= max(highs[:-1]) and lows[-1] <= min(lows[:-1]):
                parts.append("5M structure: Lower-Highs/Lower-Lows")
            else:
                parts.append("5M structure: Mixed/Ranging")

        return "; ".join(parts) if parts else "insufficient higher-timeframe data"
