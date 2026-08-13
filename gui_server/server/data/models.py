"""
Data models for the AegisVision AI Trading Server (GUI version)
Essential models without backtesting components
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum
import json

class TimeFrame(Enum):
    """Supported timeframes"""
    M1 = "1min"
    M5 = "5min"
    H1 = "1hour"

@dataclass
class TechnicalIndicators:
    """Technical indicators for a candle."""
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    ma_5: Optional[float] = None
    ma_20: Optional[float] = None
    ma_50: Optional[float] = None
    # New indicators
    obv: Optional[float] = None  # On Balance Volume
    atr: Optional[float] = None  # Average True Range
    adx: Optional[float] = None  # Average Directional Index

@dataclass
class CandleData:
    """Represents a single trading candle with technical indicators."""
    symbol: str
    timeframe: str
    timestamp: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int
    spread: float = 0.0
    technical_indicators: Optional[TechnicalIndicators] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert candle data to dictionary."""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat(),
            "open_price": self.open_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "close_price": self.close_price,
            "volume": self.volume,
            "spread": self.spread,
            "technical_indicators": self.technical_indicators.__dict__ if self.technical_indicators else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CandleData':
        """Create CandleData from dictionary."""
        timestamp = data.get('timestamp')
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        elif timestamp is None:
            timestamp = datetime.now()
        
        # Handle technical indicators
        tech_indicators = None
        if 'technical_indicators' in data and data['technical_indicators']:
            tech_indicators = TechnicalIndicators(**data['technical_indicators'])
        elif any(key in data for key in ['rsi', 'macd', 'bb_upper', 'bb_middle', 'bb_lower', 'ma_5', 'ma_20', 'ma_50']):
            tech_indicators = TechnicalIndicators(
                rsi=data.get('rsi'),
                macd=data.get('macd'),
                macd_signal=data.get('macd_signal'),
                macd_histogram=data.get('macd_histogram'),
                bb_upper=data.get('bb_upper'),
                bb_middle=data.get('bb_middle'),
                bb_lower=data.get('bb_lower'),
                ma_5=data.get('ma_5'),
                ma_20=data.get('ma_20'),
                ma_50=data.get('ma_50'),
                obv=data.get('obv'),
                atr=data.get('atr'),
                adx=data.get('adx')
            )
            
        return cls(
            symbol=data.get('symbol', ''),
            timeframe=data.get('timeframe', ''),
            timestamp=timestamp,
            open_price=float(data.get('open', data.get('open_price', 0))),
            high_price=float(data.get('high', data.get('high_price', 0))),
            low_price=float(data.get('low', data.get('low_price', 0))),
            close_price=float(data.get('close', data.get('close_price', 0))),
            volume=int(data.get('volume', 0)),
            spread=float(data.get('spread', 0)),
            technical_indicators=tech_indicators
        )

@dataclass
class MarketData:
    """Market data for LLM analysis - simplified structure"""
    symbol: str
    timeframe: str  
    timestamp: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int
    spread: float
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    bollinger_upper: Optional[float] = None
    bollinger_lower: Optional[float] = None
    moving_average_20: Optional[float] = None
    moving_average_50: Optional[float] = None

@dataclass
class WindowData:
    """Contains sliding window data for analysis."""
    symbol: str
    candles_1min: List[CandleData] = field(default_factory=list)
    candles_5min: List[CandleData] = field(default_factory=list)
    candles_1hour: List[CandleData] = field(default_factory=list)
    last_update: Optional[datetime] = None
    connection_id: str = ""
    last_analyzed_candle_timestamp: Optional[datetime] = None  # Track last analyzed candle to prevent duplicates

@dataclass
class MarketSummary:
    """Processed market summary for LLM analysis."""
    symbol: str
    timestamp: datetime
    current_price: float
    current_candle_data: Dict[str, Any] = field(default_factory=dict)
    analysis_1min: Dict[str, Any] = field(default_factory=dict)
    analysis_5min: Dict[str, Any] = field(default_factory=dict)
    analysis_1hour: Dict[str, Any] = field(default_factory=dict)
    trend_analysis: Dict[str, Any] = field(default_factory=dict)
    support_resistance_levels: Dict[str, Any] = field(default_factory=dict)
    volatility_metrics: Dict[str, Any] = field(default_factory=dict)
    momentum_indicators: Dict[str, Any] = field(default_factory=dict)
    data_quality: Dict[str, Any] = field(default_factory=dict)
    
    def to_llm_summary(self) -> str:
        """Convert to LLM-friendly summary string."""
        summary_parts = [
            f"=== MARKET ANALYSIS FOR {self.symbol} ===",
            f"Current Time: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Current Price: {self.current_price:.5f}",
            ""
        ]
        
        # Add trend analysis
        if self.trend_analysis:
            summary_parts.append("--- TREND ANALYSIS ---")
            for timeframe, trend in self.trend_analysis.items():
                if isinstance(trend, dict) and 'direction' in trend:
                    summary_parts.append(f"{timeframe}: {trend['direction']} ({trend.get('strength', 'unknown')} strength)")
        
        # Add short-term analysis
        if self.analysis_5min:
            summary_parts.append("\n--- SHORT-TERM (5min) ---")
            analysis = self.analysis_5min
            if 'price_action' in analysis:
                pa = analysis['price_action']
                summary_parts.append(f"Recent price change: {pa.get('total_change_percent', 0):.2f}% ({pa.get('trend_direction', 'unknown')})")
        
        # Add medium-term analysis
        if self.analysis_1hour:
            summary_parts.append("\n--- MEDIUM-TERM (1hour) ---")
            analysis = self.analysis_1hour
            if 'periods' in analysis:
                for period, data in analysis['periods'].items():
                    if isinstance(data, dict):
                        change = data.get('total_change_percent', 0)
                        direction = data.get('trend_direction', 'unknown')
                        summary_parts.append(f"{period}: {change:.2f}% change ({direction})")
        
        # Add support/resistance
        if self.support_resistance_levels:
            sr = self.support_resistance_levels
            summary_parts.append("\n--- KEY LEVELS ---")
            if sr.get('nearest_support'):
                summary_parts.append(f"Nearest Support: {sr['nearest_support']:.5f}")
            if sr.get('nearest_resistance'):
                summary_parts.append(f"Nearest Resistance: {sr['nearest_resistance']:.5f}")
        
        return "\n".join(summary_parts)

@dataclass 
class TradingSignal:
    """Trading signal response."""
    action: str  # BUY, SELL, WAIT
    confidence: float  # 0-100
    reasoning: str
    timestamp: Optional[datetime] = None
    symbol: str = ""
    timeframe: str = ""
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trade_management: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "action": self.action,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "trade_management": self.trade_management
        }

@dataclass
class DataRequest:
    """Request structure for data processing."""
    request_type: str  # 'bulk_load', 'update', 'reconnect'
    symbol: str
    connection_id: str
    candle_data: Optional[CandleData] = None
    bulk_1min_data: Optional[List[CandleData]] = None
    bulk_5min_data: Optional[List[CandleData]] = None
    bulk_1hour_data: Optional[List[CandleData]] = None