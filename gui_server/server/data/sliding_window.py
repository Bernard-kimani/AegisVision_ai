"""
Sliding Window Manager for AegisVision AI Trading Server (GUI version)
Manages historical candle data without backtesting features
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging
from collections import deque
from .models import CandleData, WindowData, TimeFrame

logger = logging.getLogger(__name__)

class SlidingWindowManager:
    """Manages sliding window data for 5-minute and 1-hour candles."""
    
    def __init__(self):
        # Store data per symbol/connection
        self.windows: Dict[str, WindowData] = {}
        
        # Window sizes
        self.window_1min_size = 6 * 60   # 6 hours * 60 one-minute candles per hour = 360 candles
        self.window_5min_size = 24 * 12  # 24 hours * 12 five-minute candles per hour = 288 candles
        self.window_1hour_size = 48      # 48 hours of 1-hour candles

        logger.info(f"SlidingWindowManager initialized with window sizes: "
                   f"1min={self.window_1min_size}, 5min={self.window_5min_size}, 1hour={self.window_1hour_size}")
        
    def create_connection(self, symbol: str, connection_id: str = "default") -> str:
        """Create a new connection and initialize empty windows."""
        window_key = f"{symbol}_{connection_id}"
        
        self.windows[window_key] = WindowData(
            symbol=symbol,
            candles_1min=[],
            candles_5min=[],
            candles_1hour=[],
            last_update=datetime.now(),
            connection_id=connection_id
        )
        
        logger.info(f"Created new sliding window for {symbol} (connection: {connection_id})")
        return window_key
    
    def add_candle(self, window_key: str, candle: CandleData, timeframe: str = None) -> bool:
        """Add new candle data to appropriate window (sliding window behavior)."""
        if window_key not in self.windows:
            # Auto-create window if not exists
            parts = window_key.split('_')
            symbol = parts[0] if parts else 'XAUUSD'
            connection_id = '_'.join(parts[1:]) if len(parts) > 1 else 'default'
            self.create_connection(symbol, connection_id)
            
        window = self.windows[window_key]
        
        try:
            # Use provided timeframe or candle's timeframe
            tf = timeframe or candle.timeframe
            
            # Determine timeframe and add to appropriate window
            if tf in ["M1", "PERIOD_M1", "1min"]:
                # Check for duplicate (idempotency)
                if window.candles_1min and window.candles_1min[-1].timestamp == candle.timestamp:
                    # Update existing candle instead of appending
                    window.candles_1min[-1] = candle
                    logger.debug(f"Updated existing 1min candle: {candle.timestamp}")
                else:
                    # Add new candle
                    window.candles_1min.append(candle)

                # Remove oldest candle if window is full
                if len(window.candles_1min) > self.window_1min_size:
                    removed = window.candles_1min.pop(0)
                    logger.debug(f"Removed oldest 1min candle: {removed.timestamp}")

                logger.debug(f"Added 1min candle for {window.symbol} - Window size: {len(window.candles_1min)}")

            elif tf in ["M5", "PERIOD_M5", "5min"]:
                # Check for duplicate (idempotency)
                if window.candles_5min and window.candles_5min[-1].timestamp == candle.timestamp:
                    # Update existing candle instead of appending
                    window.candles_5min[-1] = candle
                    logger.debug(f"Updated existing 5min candle: {candle.timestamp}")
                else:
                    # Add new candle
                    window.candles_5min.append(candle)
                
                # Remove oldest candle if window is full
                if len(window.candles_5min) > self.window_5min_size:
                    removed = window.candles_5min.pop(0)
                    logger.debug(f"Removed oldest 5min candle: {removed.timestamp}")
                
                logger.debug(f"Added 5min candle for {window.symbol} - Window size: {len(window.candles_5min)}")
                
            elif tf in ["H1", "PERIOD_H1", "1hour"]:
                # Check for duplicate (idempotency)
                if window.candles_1hour and window.candles_1hour[-1].timestamp == candle.timestamp:
                    # Update existing candle instead of appending
                    window.candles_1hour[-1] = candle
                    logger.debug(f"Updated existing 1hour candle: {candle.timestamp}")
                else:
                    # Add new candle
                    window.candles_1hour.append(candle)
                
                # Remove oldest candle if window is full
                if len(window.candles_1hour) > self.window_1hour_size:
                    removed = window.candles_1hour.pop(0)
                    logger.debug(f"Removed oldest 1hour candle: {removed.timestamp}")
                
                logger.debug(f"Added 1hour candle for {window.symbol} - Window size: {len(window.candles_1hour)}")
                
            else:
                logger.warning(f"Unknown timeframe: {tf}")
                return False
                
            window.last_update = datetime.now()
            return True
            
        except Exception as e:
            logger.error(f"Error adding candle data: {e}")
            return False
    
    def bulk_load_data(self, window_key: str, candles_5min: List[CandleData],
                      candles_1hour: List[CandleData], candles_1min: Optional[List[CandleData]] = None) -> bool:
        """Bulk load initial historical data (first connection or reconnection)."""
        if window_key not in self.windows:
            # Auto-create window if not exists
            parts = window_key.split('_')
            symbol = parts[0] if parts else 'XAUUSD'
            connection_id = '_'.join(parts[1:]) if len(parts) > 1 else 'default'
            self.create_connection(symbol, connection_id)

        window = self.windows[window_key]

        try:
            # Clear existing data
            window.candles_1min.clear()
            window.candles_5min.clear()
            window.candles_1hour.clear()

            # Load 1-minute data (keep only last window size worth)
            if candles_1min:
                sorted_1min = sorted(candles_1min, key=lambda x: x.timestamp)
                recent_1min = sorted_1min[-self.window_1min_size:] if len(sorted_1min) > self.window_1min_size else sorted_1min
                window.candles_1min.extend(recent_1min)
                logger.info(f"Loaded {len(window.candles_1min)} 1min candles (from {len(candles_1min)} provided)")

            # Load 5-minute data (keep only last window size worth)
            if candles_5min:
                # Sort by timestamp to ensure correct order
                sorted_5min = sorted(candles_5min, key=lambda x: x.timestamp)
                
                # Take only the most recent candles up to window size
                recent_5min = sorted_5min[-self.window_5min_size:] if len(sorted_5min) > self.window_5min_size else sorted_5min
                
                window.candles_5min.extend(recent_5min)
                logger.info(f"Loaded {len(window.candles_5min)} 5min candles (from {len(candles_5min)} provided)")
                    
            # Load 1-hour data (keep only last window size worth)  
            if candles_1hour:
                # Sort by timestamp to ensure correct order
                sorted_1hour = sorted(candles_1hour, key=lambda x: x.timestamp)
                
                # Take only the most recent candles up to window size
                recent_1hour = sorted_1hour[-self.window_1hour_size:] if len(sorted_1hour) > self.window_1hour_size else sorted_1hour
                
                window.candles_1hour.extend(recent_1hour)
                logger.info(f"Loaded {len(window.candles_1hour)} 1hour candles (from {len(candles_1hour)} provided)")
                    
            window.last_update = datetime.now()
            
            logger.info(f"Bulk loaded data for {window.symbol}: "
                       f"{len(window.candles_1min)} 1min candles, "
                       f"{len(window.candles_5min)} 5min candles, "
                       f"{len(window.candles_1hour)} 1hour candles")
            return True
            
        except Exception as e:
            logger.error(f"Error bulk loading data: {e}")
            return False
    
    def get_window_data(self, window_key: str) -> Optional[WindowData]:
        """Get window data for analysis."""
        return self.windows.get(window_key)
    
    def cleanup_connection(self, window_key: str) -> bool:
        """Clean up connection data."""
        if window_key in self.windows:
            symbol = self.windows[window_key].symbol
            del self.windows[window_key]
            logger.info(f"Cleaned up window data for {window_key} ({symbol})")
            return True
        return False
    
    def get_window_status(self, window_key: str) -> Dict[str, any]:
        """Get status information about the window."""
        if window_key not in self.windows:
            return {"error": "Window not found"}
            
        window = self.windows[window_key]

        # Calculate data coverage
        data_coverage_1min = (len(window.candles_1min) / self.window_1min_size) * 100
        data_coverage_5min = (len(window.candles_5min) / self.window_5min_size) * 100
        data_coverage_1hour = (len(window.candles_1hour) / self.window_1hour_size) * 100

        # Check if windows have sufficient data for analysis
        # Require minimum candles before starting analysis to prevent excessive LLM requests
        min_required_1min = 30  # Require at least 30 one-minute candles (30 minutes of data)
        min_required_5min = 20  # Require at least 20 five-minute candles (100 minutes of data)
        min_required_1hour = 5  # Require at least 5 one-hour candles (5 hours of data)

        sufficient_1min = len(window.candles_1min) >= min_required_1min
        sufficient_5min = len(window.candles_5min) >= min_required_5min
        sufficient_1hour = len(window.candles_1hour) >= min_required_1hour

        return {
            "symbol": window.symbol,
            "connection_id": window.connection_id,
            "candles_1min_count": len(window.candles_1min),
            "candles_5min_count": len(window.candles_5min),
            "candles_1hour_count": len(window.candles_1hour),
            "max_1min_count": self.window_1min_size,
            "max_5min_count": self.window_5min_size,
            "max_1hour_count": self.window_1hour_size,
            "data_coverage_1min_percent": round(data_coverage_1min, 2),
            "data_coverage_5min_percent": round(data_coverage_5min, 2),
            "data_coverage_1hour_percent": round(data_coverage_1hour, 2),
            "sufficient_data_1min": sufficient_1min,
            "sufficient_data_5min": sufficient_5min,
            "sufficient_data_1hour": sufficient_1hour,
            "ready_for_analysis": sufficient_1min and sufficient_5min and sufficient_1hour,  # Require ALL three timeframes
            "last_update": window.last_update.isoformat() if window.last_update else None,
            "oldest_1min_candle": window.candles_1min[0].timestamp.isoformat() if window.candles_1min else None,
            "newest_1min_candle": window.candles_1min[-1].timestamp.isoformat() if window.candles_1min else None,
            "oldest_5min_candle": window.candles_5min[0].timestamp.isoformat() if window.candles_5min else None,
            "newest_5min_candle": window.candles_5min[-1].timestamp.isoformat() if window.candles_5min else None,
            "oldest_1hour_candle": window.candles_1hour[0].timestamp.isoformat() if window.candles_1hour else None,
            "newest_1hour_candle": window.candles_1hour[-1].timestamp.isoformat() if window.candles_1hour else None,
        }
    
    def get_all_connections(self) -> List[Dict[str, any]]:
        """Get status of all active connections."""
        connections = []
        for window_key in self.windows:
            status = self.get_window_status(window_key)
            status["window_key"] = window_key
            connections.append(status)
        return connections
    
    def is_ready_for_analysis(self, window_key: str) -> bool:
        """Check if window has sufficient data for meaningful analysis."""
        status = self.get_window_status(window_key)
        if "error" in status:
            return False
            
        # Need at least 50% of both windows for reliable analysis
        return status.get("ready_for_analysis", False)

    def mark_analyzed(self, window_key: str) -> bool:
        """Mark the current latest candle as analyzed."""
        if window_key not in self.windows:
            return False
            
        window = self.windows[window_key]
        if window.candles_5min:
            window.last_analyzed_candle_timestamp = window.candles_5min[-1].timestamp
            logger.info(f"Marked candle {window.last_analyzed_candle_timestamp} as analyzed")
            return True
        return False

    def has_been_analyzed(self, window_key: str) -> bool:
        """Check if the current latest candle has already been analyzed."""
        if window_key not in self.windows:
            return False
            
        window = self.windows[window_key]
        if not window.candles_5min:
            return False
            
        current_timestamp = window.candles_5min[-1].timestamp
        
        # If we have a record of the last analyzed candle, compare timestamps
        if window.last_analyzed_candle_timestamp:
            if current_timestamp == window.last_analyzed_candle_timestamp:
                return True
                
        return False
    
    def get_data_age(self, window_key: str) -> Dict[str, any]:
        """Get information about data freshness."""
        if window_key not in self.windows:
            return {"error": "Window not found"}
            
        window = self.windows[window_key]
        now = datetime.now()
        
        result = {
            "last_update_minutes_ago": None,
            "newest_5min_age_minutes": None,
            "newest_1hour_age_minutes": None,
            "data_freshness": "unknown"
        }
        
        if window.last_update:
            result["last_update_minutes_ago"] = (now - window.last_update).total_seconds() / 60
            
        if window.candles_5min:
            newest_5min_age = (now - window.candles_5min[-1].timestamp).total_seconds() / 60
            result["newest_5min_age_minutes"] = newest_5min_age
            
        if window.candles_1hour:
            newest_1hour_age = (now - window.candles_1hour[-1].timestamp).total_seconds() / 60
            result["newest_1hour_age_minutes"] = newest_1hour_age
            
        # Determine freshness
        if result["newest_5min_age_minutes"] is not None:
            if result["newest_5min_age_minutes"] <= 10:  # Within 10 minutes
                result["data_freshness"] = "fresh"
            elif result["newest_5min_age_minutes"] <= 60:  # Within 1 hour
                result["data_freshness"] = "acceptable" 
            else:
                result["data_freshness"] = "stale"
                
        return result