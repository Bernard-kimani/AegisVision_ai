import pandas as pd
import mplfinance as mpf
import io
import base64
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

def generate_candle_chart(
    candles_data: List[dict], title: str = "Market Chart", interval_minutes: int = 5, mav: Optional[int] = None
) -> Optional[str]:
    """
    Generates a minimalist candlestick chart from candle data and returns a Base64 string.

    Args:
        candles_data: List of dictionaries containing 'timestamp', 'open_price', 'high_price', 'low_price', 'close_price', 'volume'.
                      Can be objects or dicts. If objects, they will be converted.
        title: Chart title (not used in minimalist mode but kept for compatibility).
        interval_minutes: Candle spacing, used only for the right-side padding gap.
                      Pass 1 for M1 charts, 60 for H1 charts, etc. - defaults to 5 (M5).
        mav: Optional moving-average period to overlay on the chart (e.g. 20 for the
             pullback strategy's 20 EMA line). None draws no overlay.

    Returns:
        str: Base64 encoded PNG image, or None if generation fails.
    """
    try:
        min_candles = max(5, (mav or 0) + 1)
        if not candles_data or len(candles_data) < min_candles:
            logger.warning("Insufficient data to generate chart")
            return None

        # Convert simple objects to dicts if necessary
        clean_data = []
        for c in candles_data:
            if hasattr(c, 'timestamp'):
                # It's a CandleData object
                item = {
                    'Date': c.timestamp,
                    'Open': float(c.open_price),
                    'High': float(c.high_price),
                    'Low': float(c.low_price),
                    'Close': float(c.close_price),
                    'Volume': float(c.volume)
                }
                clean_data.append(item)
            elif isinstance(c, dict):
                # It's a dictionary
                # Map keys if necessary, assuming standard keys might vary
                item = {
                    'Date': pd.to_datetime(c.get('timestamp') or c.get('time')),
                    'Open': float(c.get('open_price') or c.get('open')),
                    'High': float(c.get('high_price') or c.get('high')),
                    'Low': float(c.get('low_price') or c.get('low')),
                    'Close': float(c.get('close_price') or c.get('close')),
                    'Volume': float(c.get('volume', 0))
                }
                clean_data.append(item)

        if not clean_data:
            return None

        df = pd.DataFrame(clean_data)
        df.set_index('Date', inplace=True)

        # Compute the MA overlay (EMA, to match the EA's iMA(MODE_EMA) trend line)
        # BEFORE padding, so the trailing empty "future" rows don't get pulled into
        # the average - reindexing after leaves them NaN, which mplfinance simply
        # breaks the line on rather than projecting a fake flat continuation.
        addplots = []
        if mav:
            ema_series = df['Close'].ewm(span=mav, adjust=False).mean()

        # Add "future" empty candles for right-side clearance (~5% padding)
        # This ensures the latest candles aren't squashed against the Y-axis
        last_date = df.index[-1]
        future_dates = [last_date + pd.Timedelta(minutes=interval_minutes * i) for i in range(1, 15)]
        future_df = pd.DataFrame(index=future_dates, columns=df.columns, dtype=float)
        df = pd.concat([df, future_df])

        if mav:
            addplots.append(mpf.make_addplot(ema_series.reindex(df.index), color='blue', width=1.0))

        # Create plot in memory
        buf = io.BytesIO()

        # Style: 'charles' is a standard red/green candle style
        # Custom style: Hide grid to reduce noise, but keep axes for Price Levels
        mc = mpf.make_marketcolors(up='green', down='red', inherit=True)
        # Use gridstyle='' to hide grid lines effectively
        s  = mpf.make_mpf_style(marketcolors=mc, gridstyle='')

        plot_kwargs = dict(
            type='candle',
            style=s,
            axisoff=False,   # Keep axes enabled so we can see Y-axis (Price)
            volume=False,    # Volume can clutter the main view
            figsize=(10, 4), # OPTIMIZED SMALLER ASPECT RATIO FOR LLM SPEED
            ylabel='',       # Hide "Price" label text, keep the numbers
            returnfig=True,
        )
        if addplots:
            plot_kwargs['addplot'] = addplots

        # We use returnfig=True to get access to axes for fine-tuning
        # Fast compute size: (10, 4) saves base64 encoding and processing time
        fig, axlist = mpf.plot(df, **plot_kwargs)

        # Hide X-axis timestamps explicitly
        ax = axlist[0]
        ax.xaxis.set_visible(False) # Hide X labels and ticks
        
        # Save explicitly from figure
        fig.savefig(buf, bbox_inches='tight', pad_inches=0.1)

        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        return img_base64

    except Exception as e:
        logger.error(f"Error generating chart: {e}")
        return None
