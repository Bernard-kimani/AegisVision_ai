"""
Agent 1: Data Ingestor & Preprocessor.

Owns the sliding-window buffers and turns them into what Agent 2 needs: a text
market summary plus a fast-rendered chart image. This wraps the existing
SlidingWindowManager/DataPreprocessor/chart_generator - it doesn't reimplement
them, it just gives the rest of the pipeline one narrow interface to depend on.

Also computes the deterministic trigger metrics (stop-loss/take-profit,
headroom to the nearest liquidity pool, risk:reward, higher-timeframe bias)
that feed the Agent 2 vision prompt. These are plain arithmetic over the
buffered candles, not an LLM call - direction comes from Agent 0's trigger
(EA), Agent 2 only judges whether the visual setup looks like the reference
template, it doesn't invent a trade plan.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from data.models import CandleData
from data.preprocessor import DataPreprocessor
from data.sliding_window import SlidingWindowManager
from utils.chart_generator import generate_candle_chart

logger = logging.getLogger(__name__)

# Chart is rendered from the M1 tier by default: the strategy's trigger and
# the 20 EMA line it trades against both live on the 1-minute chart, so that's
# the "Image C" the vision-compliance agent needs to see. Swappable per-call.
CHART_TIMEFRAME_INTERVAL_MINUTES = {"M1": 1, "M5": 5, "H1": 60}
TIMEFRAME_TO_WINDOW_ATTR = {"M1": "candles_1min", "M5": "candles_5min", "H1": "candles_1hour"}

STRATEGY_EMA_PERIOD = 20  # must match the EA's EMA_Period input
SL_LOOKBACK_CANDLES = 3   # must match the EA's SL_LookbackBars input
# Must match the EA's SL_BufferPoints input x the broker's point size
# (e.g. 100 points x $0.01 = $1.00 for a 2-digit XAUUSD quote). Update this
# if SL_BufferPoints changes or the broker quotes gold at different precision.
SL_BUFFER_PRICE = 1.00
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
    """Deterministic (non-LLM) numbers computed for a signal event, matching
    the placeholders in Agent 2's production prompt template."""
    direction: str  # BUY | SELL
    stop_loss: Optional[float]
    take_profit: Optional[float]
    risk_reward: Optional[float]
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

        summary = self.preprocessor.generate_market_summary(window_key)
        if not summary:
            logger.warning(f"Could not generate market summary for {window_key}")
            return None

        market_summary_text = self.preprocessor.format_for_llm(summary)

        chart_b64 = None
        try:
            window_data = self.window_manager.get_window_data(window_key)
            attr = TIMEFRAME_TO_WINDOW_ATTR.get(chart_timeframe, "candles_5min")
            candles = getattr(window_data, attr, None) if window_data else None
            if candles:
                recent = candles[-180:] if len(candles) > 180 else candles
                interval = CHART_TIMEFRAME_INTERVAL_MINUTES.get(chart_timeframe, 5)
                mav = STRATEGY_EMA_PERIOD if chart_timeframe == "M1" else None
                chart_b64 = generate_candle_chart(
                    recent, title=f"{symbol} {chart_timeframe}", interval_minutes=interval, mav=mav
                )
        except Exception as e:
            logger.error(f"Failed to generate chart image for {window_key}: {e}")

        return IngestorPayload(
            symbol=symbol,
            market_summary_text=market_summary_text,
            chart_image_b64=chart_b64,
            chart_timeframe=chart_timeframe,
            open_trades=open_trades or [],
        )

    # --- Deterministic trigger metrics (SL/TP/headroom/R:R/higher-tf bias) ---

    def compute_trigger_metrics(self, symbol: str, direction: str) -> Optional[TriggerMetrics]:
        window_data = self.window_manager.get_window_data(self.window_key_for(symbol))
        if not window_data or not window_data.candles_1min:
            return None

        m1 = window_data.candles_1min
        m5 = window_data.candles_5min
        h1 = window_data.candles_1hour
        current_price = m1[-1].close_price

        recent_extreme_window = m1[-SL_LOOKBACK_CANDLES:] if len(m1) >= SL_LOOKBACK_CANDLES else m1
        buffer = SL_BUFFER_PRICE

        if direction == "BUY":
            recent_extreme = min(c.low_price for c in recent_extreme_window)
            stop_loss = recent_extreme - buffer
        else:
            recent_extreme = max(c.high_price for c in recent_extreme_window)
            stop_loss = recent_extreme + buffer

        target_5m = self._find_swing_target(m5, direction)
        target_1h = self._find_swing_target(h1, direction)
        candidates = [t for t in (target_5m, target_1h) if t is not None]
        if direction == "BUY":
            candidates = [t for t in candidates if t > current_price]
            take_profit = min(candidates) if candidates else None
        else:
            candidates = [t for t in candidates if t < current_price]
            take_profit = max(candidates) if candidates else None

        risk_reward = None
        headroom_pips = None
        if take_profit is not None:
            risk = abs(current_price - stop_loss)
            reward = abs(take_profit - current_price)
            headroom_pips = reward
            if risk > 0:
                risk_reward = reward / risk

        bias = self._compute_higher_timeframe_bias(h1, m5)

        return TriggerMetrics(
            direction=direction,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=risk_reward,
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
