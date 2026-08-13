"""
Data Preprocessor for AegisVision AI Trading Server (GUI version)
Simplified version without backtesting components
"""

import logging
import statistics
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from .models import CandleData, WindowData, MarketSummary, TechnicalIndicators
from .sliding_window import SlidingWindowManager

logger = logging.getLogger(__name__)

class DataPreprocessor:
    """Processes sliding window data and generates market summaries for LLM analysis"""
    
    def __init__(self, sliding_window_manager: SlidingWindowManager):
        self.sliding_window_manager = sliding_window_manager
        logger.info("DataPreprocessor initialized")

    def generate_market_summary(self, window_key: str) -> Optional[MarketSummary]:
        """Generate comprehensive market summary from sliding window data"""
        try:
            window_data = self.sliding_window_manager.get_window_data(window_key)
            if not window_data:
                logger.error(f"No window data found for {window_key}")
                return None
            
            if not window_data.candles_5min:
                logger.warning(f"No 5min candles available for {window_key}")
                return None
            
            # Inject missing indicators if needed
            self._inject_missing_indicators(window_data)
            
            # Get current price and candle info
            current_candle = window_data.candles_5min[-1]
            current_price = current_candle.close_price
            
            # Debug: Log current candle data
            logger.info(f"DEBUG - Current candle close_price: {current_candle.close_price}")
            logger.info(f"DEBUG - Current candle technical_indicators: {current_candle.technical_indicators}")
            
            # Analyze different timeframes
            analysis_1min = self._analyze_1min_data(window_data.candles_1min)
            analysis_5min = self._analyze_5min_data(window_data.candles_5min)
            analysis_1hour = self._analyze_1hour_data(window_data.candles_1hour)
            
            # Trend analysis
            trend_analysis = self._analyze_trends(window_data)
            
            # Support/Resistance levels
            support_resistance = self._calculate_support_resistance(window_data.candles_5min, window_data.candles_1hour)
            
            # Volatility metrics
            volatility_metrics = self._calculate_volatility_metrics(window_data)
            
            # Current candle technical indicators
            current_candle_data = self._format_current_candle_data(current_candle)
            
            # Data quality info
            data_quality = self._assess_data_quality(window_data)
            
            return MarketSummary(
                symbol=window_data.symbol,
                timestamp=current_candle.timestamp,
                current_price=current_price,
                current_candle_data=current_candle_data,
                analysis_1min=analysis_1min,
                analysis_5min=analysis_5min,
                analysis_1hour=analysis_1hour,
                trend_analysis=trend_analysis,
                support_resistance_levels=support_resistance,
                volatility_metrics=volatility_metrics,
                data_quality=data_quality
            )
            
        except Exception as e:
            logger.error(f"Error generating market summary: {e}")
            return None
    
    def _format_current_candle_data(self, candle: CandleData) -> Dict[str, Any]:
        """Format current candle data including technical indicators"""
        data = {
            'open': candle.open_price,
            'high': candle.high_price,
            'low': candle.low_price,
            'close': candle.close_price,
            'volume': candle.volume,
            'spread': candle.spread
        }
        
        # Add technical indicators if available
        if candle.technical_indicators:
            ti = candle.technical_indicators
            data.update({
                'rsi': ti.rsi,
                'macd': ti.macd,
                'macd_signal': ti.macd_signal,
                'macd_histogram': ti.macd_histogram,
                'bb_upper': ti.bb_upper,
                'bb_middle': ti.bb_middle,
                'bb_lower': ti.bb_lower,
                'ma_5': ti.ma_5,
                'ma_20': ti.ma_20,
                'ma_50': ti.ma_50,
                'obv': ti.obv,
                'atr': ti.atr,
                'adx': ti.adx
            })
        
        return data
    
    def _analyze_1min_data(self, candles: List[CandleData]) -> Dict[str, Any]:
        """Analyze 1-minute (ultra-short-term / execution trigger) timeframe data"""
        if not candles:
            return {}

        try:
            # Recent window: last 30 candles (30 minutes) for the execution-trigger horizon
            recent_candles = candles[-30:] if len(candles) >= 30 else candles

            if len(recent_candles) < 2:
                return {"error": "Insufficient data for 1min analysis"}

            start_price = recent_candles[0].close_price
            end_price = recent_candles[-1].close_price
            total_change = end_price - start_price
            total_change_percent = (total_change / start_price) * 100 if start_price > 0 else 0

            trend_direction = "upward" if total_change > 0 else "downward" if total_change < 0 else "sideways"

            highs = [c.high_price for c in recent_candles]
            lows = [c.low_price for c in recent_candles]
            volatility = (max(highs) - min(lows)) / start_price if start_price > 0 else 0

            patterns = []
            if len(recent_candles) >= 5:
                last_5_closes = [c.close_price for c in recent_candles[-5:]]
                if all(last_5_closes[i] <= last_5_closes[i+1] for i in range(4)):
                    patterns.append("Ascending micro-trend")
                elif all(last_5_closes[i] >= last_5_closes[i+1] for i in range(4)):
                    patterns.append("Descending micro-trend")
                else:
                    patterns.append("Consolidation")

            return {
                "price_action": {
                    "total_change": total_change,
                    "total_change_percent": total_change_percent,
                    "trend_direction": trend_direction,
                    "volatility": volatility,
                    "candles_analyzed": len(recent_candles)
                },
                "patterns": patterns
            }

        except Exception as e:
            logger.error(f"Error analyzing 1min data: {e}")
            return {"error": str(e)}

    def _analyze_5min_data(self, candles: List[CandleData]) -> Dict[str, Any]:
        """Analyze 5-minute timeframe data"""
        if not candles:
            return {}
        
        try:
            # Price action analysis
            recent_candles = candles[-20:] if len(candles) >= 20 else candles
            
            if len(recent_candles) < 2:
                return {"error": "Insufficient data for 5min analysis"}
            
            # Calculate price changes
            start_price = recent_candles[0].close_price
            end_price = recent_candles[-1].close_price
            total_change = end_price - start_price
            total_change_percent = (total_change / start_price) * 100 if start_price > 0 else 0
            
            # Trend direction
            trend_direction = "upward" if total_change > 0 else "downward" if total_change < 0 else "sideways"
            
            # Volatility
            highs = [c.high_price for c in recent_candles]
            lows = [c.low_price for c in recent_candles]
            volatility = (max(highs) - min(lows)) / start_price if start_price > 0 else 0
            
            # Pattern detection (simplified)
            patterns = []
            if len(recent_candles) >= 5:
                last_5_closes = [c.close_price for c in recent_candles[-5:]]
                if all(last_5_closes[i] <= last_5_closes[i+1] for i in range(4)):
                    patterns.append("Ascending trend")
                elif all(last_5_closes[i] >= last_5_closes[i+1] for i in range(4)):
                    patterns.append("Descending trend")
                else:
                    patterns.append("Consolidation")
            
            return {
                "price_action": {
                    "total_change": total_change,
                    "total_change_percent": total_change_percent,
                    "trend_direction": trend_direction,
                    "volatility": volatility,
                    "candles_analyzed": len(recent_candles)
                },
                "patterns": patterns
            }
            
        except Exception as e:
            logger.error(f"Error analyzing 5min data: {e}")
            return {"error": str(e)}
    
    def _analyze_1hour_data(self, candles: List[CandleData]) -> Dict[str, Any]:
        """Analyze 1-hour timeframe data"""
        if not candles:
            return {}
        
        try:
            analysis = {"periods": {}}
            
            # Analyze different time periods
            periods = {
                "last_6_hours": 6,
                "last_12_hours": 12,
                "last_24_hours": 24
            }
            
            for period_name, hours in periods.items():
                period_candles = candles[-hours:] if len(candles) >= hours else candles
                
                if len(period_candles) < 2:
                    continue
                
                start_price = period_candles[0].close_price
                end_price = period_candles[-1].close_price
                change = end_price - start_price
                change_percent = (change / start_price) * 100 if start_price > 0 else 0
                
                trend_direction = "upward" if change > 0 else "downward" if change < 0 else "sideways"
                
                analysis["periods"][period_name] = {
                    "total_change": change,
                    "total_change_percent": change_percent,
                    "trend_direction": trend_direction,
                    "candles_analyzed": len(period_candles)
                }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing 1hour data: {e}")
            return {"error": str(e)}
    
    def _analyze_trends(self, window_data: WindowData) -> Dict[str, Any]:
        """Analyze multi-timeframe trends"""
        try:
            trends = {}

            # 1-minute trend (execution-trigger horizon)
            if window_data.candles_1min:
                recent_1min = window_data.candles_1min[-15:] if len(window_data.candles_1min) >= 15 else window_data.candles_1min
                if len(recent_1min) >= 2:
                    start = recent_1min[0].close_price
                    end = recent_1min[-1].close_price
                    change_percent = ((end - start) / start) * 100 if start > 0 else 0

                    if change_percent > 0.05:
                        trends["1min"] = {"direction": "BULLISH", "strength": "moderate" if change_percent > 0.15 else "weak"}
                    elif change_percent < -0.05:
                        trends["1min"] = {"direction": "BEARISH", "strength": "moderate" if change_percent < -0.15 else "weak"}
                    else:
                        trends["1min"] = {"direction": "NEUTRAL", "strength": "weak"}

            # 5-minute trend
            if window_data.candles_5min:
                recent_5min = window_data.candles_5min[-10:] if len(window_data.candles_5min) >= 10 else window_data.candles_5min
                if len(recent_5min) >= 2:
                    start = recent_5min[0].close_price
                    end = recent_5min[-1].close_price
                    change_percent = ((end - start) / start) * 100 if start > 0 else 0
                    
                    if change_percent > 0.1:
                        trends["5min"] = {"direction": "BULLISH", "strength": "moderate" if change_percent > 0.3 else "weak"}
                    elif change_percent < -0.1:
                        trends["5min"] = {"direction": "BEARISH", "strength": "moderate" if change_percent < -0.3 else "weak"}
                    else:
                        trends["5min"] = {"direction": "NEUTRAL", "strength": "weak"}
            
            # 1-hour trend
            if window_data.candles_1hour:
                recent_1hour = window_data.candles_1hour[-5:] if len(window_data.candles_1hour) >= 5 else window_data.candles_1hour
                if len(recent_1hour) >= 2:
                    start = recent_1hour[0].close_price
                    end = recent_1hour[-1].close_price
                    change_percent = ((end - start) / start) * 100 if start > 0 else 0
                    
                    if change_percent > 0.2:
                        trends["1hour"] = {"direction": "BULLISH", "strength": "strong" if change_percent > 0.5 else "moderate"}
                    elif change_percent < -0.2:
                        trends["1hour"] = {"direction": "BEARISH", "strength": "strong" if change_percent < -0.5 else "moderate"}
                    else:
                        trends["1hour"] = {"direction": "NEUTRAL", "strength": "weak"}
            
            # 4-hour trend (using 1-hour data)
            if len(window_data.candles_1hour) >= 8:
                recent_4hour = window_data.candles_1hour[-8:]
                start = recent_4hour[0].close_price
                end = recent_4hour[-1].close_price
                change_percent = ((end - start) / start) * 100 if start > 0 else 0
                
                if change_percent > 0.4:
                    trends["4hour"] = {"direction": "BULLISH", "strength": "strong" if change_percent > 1.0 else "moderate"}
                elif change_percent < -0.4:
                    trends["4hour"] = {"direction": "BEARISH", "strength": "strong" if change_percent < -1.0 else "moderate"}
                else:
                    trends["4hour"] = {"direction": "NEUTRAL", "strength": "weak"}
            
            # Calculate trend alignment
            if len(trends) >= 2:
                bullish_count = sum(1 for t in trends.values() if t["direction"] == "BULLISH")
                bearish_count = sum(1 for t in trends.values() if t["direction"] == "BEARISH")
                total_trends = len(trends)
                
                if bullish_count / total_trends >= 0.7:
                    alignment = {"status": "BULLISH_ALIGNED", "confidence": bullish_count / total_trends}
                elif bearish_count / total_trends >= 0.7:
                    alignment = {"status": "BEARISH_ALIGNED", "confidence": bearish_count / total_trends}
                else:
                    alignment = {"status": "MIXED", "confidence": max(bullish_count, bearish_count) / total_trends}
                
                trends["alignment"] = alignment
            
            return trends
            
        except Exception as e:
            logger.error(f"Error analyzing trends: {e}")
            return {}
    
    def _calculate_support_resistance(self, candles_5min: List[CandleData], candles_1hour: List[CandleData]) -> Dict[str, Any]:
        """Calculate support and resistance levels"""
        try:
            levels = {}
            
            # Use 5-minute data for recent levels
            if candles_5min and len(candles_5min) >= 20:
                recent_candles = candles_5min[-50:] if len(candles_5min) >= 50 else candles_5min
                
                # Simple support/resistance calculation
                highs = [c.high_price for c in recent_candles]
                lows = [c.low_price for c in recent_candles]
                
                # Find recent significant levels
                current_price = candles_5min[-1].close_price
                
                # Resistance: recent highs above current price
                resistance_candidates = [h for h in highs if h > current_price]
                if resistance_candidates:
                    levels["nearest_resistance"] = min(resistance_candidates)
                
                # Support: recent lows below current price  
                support_candidates = [l for l in lows if l < current_price]
                if support_candidates:
                    levels["nearest_support"] = max(support_candidates)
            
            return levels
            
        except Exception as e:
            logger.error(f"Error calculating support/resistance: {e}")
            return {}
    
    def _calculate_volatility_metrics(self, window_data: WindowData) -> Dict[str, Any]:
        """Calculate volatility metrics"""
        try:
            metrics = {}

            # 1-minute volatility
            if window_data.candles_1min and len(window_data.candles_1min) >= 10:
                recent_1min = window_data.candles_1min[-30:] if len(window_data.candles_1min) >= 30 else window_data.candles_1min

                ranges = [(c.high_price - c.low_price) / c.close_price for c in recent_1min if c.close_price > 0]
                if ranges:
                    avg_range = statistics.mean(ranges)

                    if avg_range > 0.0008:  # > 0.08%
                        vol_level = "HIGH"
                    elif avg_range > 0.0004:  # > 0.04%
                        vol_level = "MODERATE"
                    else:
                        vol_level = "LOW"

                    metrics["1min"] = {
                        "average_range_percent": avg_range * 100,
                        "volatility_level": vol_level
                    }

            # 5-minute volatility
            if window_data.candles_5min and len(window_data.candles_5min) >= 10:
                recent_5min = window_data.candles_5min[-20:] if len(window_data.candles_5min) >= 20 else window_data.candles_5min
                
                # Calculate price ranges
                ranges = [(c.high_price - c.low_price) / c.close_price for c in recent_5min if c.close_price > 0]
                if ranges:
                    avg_range = statistics.mean(ranges)
                    
                    if avg_range > 0.002:  # > 0.2%
                        vol_level = "HIGH"
                    elif avg_range > 0.001:  # > 0.1%
                        vol_level = "MODERATE"
                    else:
                        vol_level = "LOW"
                    
                    metrics["5min"] = {
                        "average_range_percent": avg_range * 100,
                        "volatility_level": vol_level
                    }
            
            # 1-hour volatility
            if window_data.candles_1hour and len(window_data.candles_1hour) >= 5:
                recent_1hour = window_data.candles_1hour[-10:] if len(window_data.candles_1hour) >= 10 else window_data.candles_1hour
                
                ranges = [(c.high_price - c.low_price) / c.close_price for c in recent_1hour if c.close_price > 0]
                if ranges:
                    avg_range = statistics.mean(ranges)
                    
                    if avg_range > 0.005:  # > 0.5%
                        vol_level = "HIGH"
                    elif avg_range > 0.003:  # > 0.3%
                        vol_level = "MODERATE"
                    else:
                        vol_level = "LOW"
                    
                    metrics["1hour"] = {
                        "average_range_percent": avg_range * 100,
                        "volatility_level": vol_level
                    }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating volatility metrics: {e}")
            return {}
    
    def _assess_data_quality(self, window_data: WindowData) -> Dict[str, Any]:
        """Assess the quality and completeness of available data"""
        return {
            "candles_1min_count": len(window_data.candles_1min),
            "candles_5min_count": len(window_data.candles_5min),
            "candles_1hour_count": len(window_data.candles_1hour),
            "last_update": window_data.last_update.isoformat() if window_data.last_update else None,
            "data_freshness": "fresh" if window_data.last_update and (datetime.now() - window_data.last_update).total_seconds() < 300 else "stale"
        }
    
    def format_for_llm(self, summary: MarketSummary) -> str:
        """Format market summary into a concise text prompt for LLM analysis."""
        try:
            prompt_parts = []
            
            # Header with current market state
            prompt_parts.append(f"=== MARKET ANALYSIS FOR {summary.symbol} ===")
            prompt_parts.append(f"Current Time: {summary.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            prompt_parts.append(f"Current Price: {summary.current_price:.5f}")
            
            # Current candle info
            if summary.current_candle_data:
                candle = summary.current_candle_data
                prompt_parts.append(f"Current 5min Candle: O:{candle.get('open', 0):.5f} H:{candle.get('high', 0):.5f} L:{candle.get('low', 0):.5f} C:{candle.get('close', 0):.5f}")
                
                # Technical indicators if available
                indicators = []
                if candle.get('rsi') is not None:
                    indicators.append(f"RSI: {candle['rsi']:.1f}")
                if candle.get('macd') is not None:
                    indicators.append(f"MACD: {candle['macd']:.6f}")
                if candle.get('macd_signal') is not None:
                    indicators.append(f"Signal: {candle['macd_signal']:.6f}")
                if candle.get('macd_histogram') is not None:
                    indicators.append(f"Histogram: {candle['macd_histogram']:.6f}")
                
                if indicators:
                    prompt_parts.append(f"Technical Indicators: {', '.join(indicators)}")
                
                # Bollinger Bands
                bb_info = []
                if candle.get('bb_upper') is not None:
                    bb_info.append(f"BB Upper: {candle['bb_upper']:.5f}")
                if candle.get('bb_middle') is not None:
                    bb_info.append(f"Middle: {candle['bb_middle']:.5f}")
                if candle.get('bb_lower') is not None:
                    bb_info.append(f"Lower: {candle['bb_lower']:.5f}")
                
                if bb_info:
                    prompt_parts.append(", ".join(bb_info))
                
                # Moving Averages
                ma_info = []
                if candle.get('ma_5') is not None:
                    ma_info.append(f"MA5: {candle['ma_5']:.5f}")
                if candle.get('ma_20') is not None:
                    ma_info.append(f"MA20: {candle['ma_20']:.5f}")
                if candle.get('ma_50') is not None:
                    ma_info.append(f"MA50: {candle['ma_50']:.5f}")
                
                if ma_info:
                    prompt_parts.append(", ".join(ma_info))
                
                # New indicators
                new_indicators = []
                if candle.get('obv') is not None:
                    new_indicators.append(f"OBV: {candle['obv']:.0f}")
                if candle.get('atr') is not None:
                    new_indicators.append(f"ATR: {candle['atr']:.6f}")
                if candle.get('adx') is not None:
                    new_indicators.append(f"ADX: {candle['adx']:.1f}")
                
                if new_indicators:
                    prompt_parts.append(", ".join(new_indicators))
            
            # Trend analysis
            if summary.trend_analysis:
                prompt_parts.append("\n--- TREND ANALYSIS ---")
                for timeframe, trend in summary.trend_analysis.items():
                    if isinstance(trend, dict) and 'direction' in trend:
                        prompt_parts.append(f"{timeframe}: {trend['direction']} ({trend.get('strength', 'unknown')} strength)")
                
                if 'alignment' in summary.trend_analysis:
                    align = summary.trend_analysis['alignment']
                    prompt_parts.append(f"Trend Alignment: {align['status']} (confidence: {align['confidence']:.1%})")
            
            # Price action summaries
            if summary.analysis_1min:
                prompt_parts.append("\n--- ULTRA-SHORT-TERM (1min, execution trigger horizon) ---")
                analysis = summary.analysis_1min

                if 'price_action' in analysis:
                    pa = analysis['price_action']
                    prompt_parts.append(f"Recent price change: {pa.get('total_change_percent', 0):.3f}% ({pa.get('trend_direction', 'unknown')})")

                if 'patterns' in analysis and analysis['patterns']:
                    prompt_parts.append(f"Patterns detected: {', '.join(analysis['patterns'])}")

            if summary.analysis_5min:
                prompt_parts.append("\n--- SHORT-TERM (5min) ---")
                analysis = summary.analysis_5min
                
                if 'price_action' in analysis:
                    pa = analysis['price_action']
                    prompt_parts.append(f"Recent price change: {pa.get('total_change_percent', 0):.2f}% ({pa.get('trend_direction', 'unknown')})")
                
                if 'patterns' in analysis and analysis['patterns']:
                    prompt_parts.append(f"Patterns detected: {', '.join(analysis['patterns'])}")
            
            if summary.analysis_1hour:
                prompt_parts.append("\n--- MEDIUM-TERM (1hour) ---")
                analysis = summary.analysis_1hour
                
                if 'periods' in analysis:
                    for period, data in analysis['periods'].items():
                        if isinstance(data, dict):
                            change = data.get('total_change_percent', 0)
                            direction = data.get('trend_direction', 'unknown')
                            prompt_parts.append(f"{period}: {change:.2f}% change ({direction})")
            
            # Support/Resistance
            if summary.support_resistance_levels:
                sr = summary.support_resistance_levels
                prompt_parts.append("\n--- KEY LEVELS ---")
                
                if sr.get('nearest_support'):
                    prompt_parts.append(f"Nearest Support: {sr['nearest_support']:.5f}")
                if sr.get('nearest_resistance'):
                    prompt_parts.append(f"Nearest Resistance: {sr['nearest_resistance']:.5f}")
            
            # Volatility
            if summary.volatility_metrics:
                prompt_parts.append("\n--- VOLATILITY ---")
                for timeframe, vol_data in summary.volatility_metrics.items():
                    if isinstance(vol_data, dict) and 'volatility_level' in vol_data:
                        prompt_parts.append(f"{timeframe}: {vol_data['volatility_level']} volatility")
            
            # Data quality note
            if summary.data_quality:
                dq = summary.data_quality
                prompt_parts.append(f"\n--- DATA COVERAGE ---")
                prompt_parts.append(f"1min candles: {dq.get('candles_1min_count', 0)}, 5min candles: {dq.get('candles_5min_count', 0)}, 1hour candles: {dq.get('candles_1hour_count', 0)}")
            
            return "\n".join(prompt_parts)
            
        except Exception as e:
            logger.error(f"Error formatting summary for LLM: {e}")
            return f"Error formatting market summary: {str(e)}"

    def _inject_missing_indicators(self, window_data: WindowData):
        """Inject OBV, ATR, ADX into technical indicators if missing."""
        candles = window_data.candles_5min
        if not candles or len(candles) < 2:
            return

        # --- OBV ---
        obv = [candles[0].volume]
        for i in range(1, len(candles)):
            if candles[i].close_price > candles[i-1].close_price:
                obv.append(obv[-1] + candles[i].volume)
            elif candles[i].close_price < candles[i-1].close_price:
                obv.append(obv[-1] - candles[i].volume)
            else:
                obv.append(obv[-1])
                
        # --- ATR (simple calculation) ---
        true_ranges = []
        for i in range(1, len(candles)):
            high_low = candles[i].high_price - candles[i].low_price
            high_close_prev = abs(candles[i].high_price - candles[i-1].close_price)
            low_close_prev = abs(candles[i].low_price - candles[i-1].close_price)
            true_ranges.append(max(high_low, high_close_prev, low_close_prev))
        atr = statistics.mean(true_ranges[-14:]) if len(true_ranges) >= 14 else (statistics.mean(true_ranges) if true_ranges else 0)

        # --- ADX (simplified calculation) ---
        adx = self._calculate_adx(candles)

        # Inject into last candle's technical indicators if missing
        last_candle = candles[-1]
        if not last_candle.technical_indicators:
            last_candle.technical_indicators = TechnicalIndicators()
        
        ti = last_candle.technical_indicators
        if ti.obv is None:
            ti.obv = obv[-1]
        if ti.atr is None:
            ti.atr = atr
        if ti.adx is None:
            ti.adx = adx

    def _calculate_adx(self, candles: List[CandleData], period: int = 14) -> float:
        """Calculate ADX (simplified version)"""
        try:
            if len(candles) < period + 1:
                return 25.0  # Default neutral value
            
            # Calculate directional movement
            dm_plus = []
            dm_minus = []
            true_ranges = []
            
            for i in range(1, len(candles)):
                high_diff = candles[i].high_price - candles[i-1].high_price
                low_diff = candles[i-1].low_price - candles[i].low_price
                
                dm_plus.append(max(high_diff, 0) if high_diff > low_diff else 0)
                dm_minus.append(max(low_diff, 0) if low_diff > high_diff else 0)
                
                high_low = candles[i].high_price - candles[i].low_price
                high_close = abs(candles[i].high_price - candles[i-1].close_price)
                low_close = abs(candles[i].low_price - candles[i-1].close_price)
                true_ranges.append(max(high_low, high_close, low_close))
            
            if not true_ranges or not dm_plus or not dm_minus:
                return 25.0
            
            # Simple ADX calculation (smoothed averages)
            recent_tr = true_ranges[-period:] if len(true_ranges) >= period else true_ranges
            recent_dm_plus = dm_plus[-period:] if len(dm_plus) >= period else dm_plus
            recent_dm_minus = dm_minus[-period:] if len(dm_minus) >= period else dm_minus
            
            avg_tr = statistics.mean(recent_tr)
            avg_dm_plus = statistics.mean(recent_dm_plus)
            avg_dm_minus = statistics.mean(recent_dm_minus)
            
            if avg_tr == 0:
                return 25.0
            
            di_plus = 100 * (avg_dm_plus / avg_tr)
            di_minus = 100 * (avg_dm_minus / avg_tr)
            
            if di_plus + di_minus == 0:
                return 25.0
            
            dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus)
            
            # Return DX as simplified ADX (normally ADX would be smoothed DX)
            return min(max(dx, 0), 100)  # Clamp between 0 and 100
            
        except Exception as e:
            logger.error(f"Error calculating ADX: {e}")
            return 25.0  # Default neutral value