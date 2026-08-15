import matplotlib
# Must happen before mplfinance (which imports matplotlib.pyplot internally)
# ever runs, and before any GUI backend gets auto-selected. Agg is the
# headless, thread-safe raster backend - required here because chart
# generation runs inside Flask request-handler threads, not the main thread,
# and GUI backends (the default matplotlib can fall back to on Windows when
# a GUI toolkit is importable) are not safe to drive off the main thread -
# doing so can hang or crash the whole process, taking the HTTP response
# down with it.
matplotlib.use('Agg')

import pandas as pd
import mplfinance as mpf
import io
import base64
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def _compute_rsi(close: "pd.Series", period: int) -> "pd.Series":
    """Standard Wilder-smoothed RSI over closing prices."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def generate_candle_chart(
    candles_data: List[dict], title: str = "Market Chart", interval_minutes: int = 5,
    mav: Optional[int] = None, rsi_period: Optional[int] = None,
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
        rsi_period: Optional period for an RSI sub-panel below the main candles
             (e.g. 14 for the standard reading). None omits the panel entirely,
             keeping the single-panel layout other timeframes still use.

    Returns:
        str: Base64 encoded PNG image, or None if generation fails.
    """
    try:
        min_candles = max(5, (mav or 0) + 1, (rsi_period or 0) + 1)
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

        # Compute the MA overlay (SMA, to match the EA's iMA(MODE_SMA) trend line)
        # BEFORE padding, so the trailing empty "future" rows don't get pulled into
        # the average - reindexing after leaves them NaN, which mplfinance simply
        # breaks the line on rather than projecting a fake flat continuation.
        addplots = []
        if mav:
            ma_series = df['Close'].rolling(window=mav).mean()
        if rsi_period:
            rsi_series = _compute_rsi(df['Close'], rsi_period)

        # Add "future" empty candles for right-side clearance (~5% padding)
        # This ensures the latest candles aren't squashed against the Y-axis
        last_date = df.index[-1]
        future_dates = [last_date + pd.Timedelta(minutes=interval_minutes * i) for i in range(1, 15)]
        future_df = pd.DataFrame(index=future_dates, columns=df.columns, dtype=float)
        df = pd.concat([df, future_df])

        if mav:
            addplots.append(mpf.make_addplot(ma_series.reindex(df.index), color='blue', width=1.0))
        if rsi_period:
            addplots.append(mpf.make_addplot(
                rsi_series.reindex(df.index), panel=1, color='purple', width=1.0, ylabel='RSI',
            ))

        # Create plot in memory
        buf = io.BytesIO()

        # Style: 'charles' is a standard red/green candle style
        # Custom style: Hide grid to reduce noise, but keep axes for Price Levels
        mc = mpf.make_marketcolors(up='green', down='red', inherit=True)
        s  = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', gridcolor='#888888')

        plot_kwargs = dict(
            type='candle',
            style=s,
            axisoff=False,   # Keep axes enabled so we can see Y-axis (Price)
            volume=False,    # Volume can clutter the main view
            # Taller when an RSI panel is added (2.2:1 split against the main
            # panel, giving RSI real height to be readable) so the candles
            # don't shrink to make room for it - otherwise identical to the
            # single-panel size below. Wide enough that 240+ candles don't
            # get squeezed to a couple pixels each - mplfinance auto-scales
            # candle/wick width off the available spacing, so a narrow
            # canvas at high candle counts is what makes wicks look
            # off-center (sub-pixel rounding on a 1px-wide line).
            figsize=(15, 6.5) if rsi_period else (14, 5),
            ylabel='',       # Hide "Price" label text, keep the numbers
            returnfig=True,
            # candle_linewidth nudged up from mplfinance's auto-scaled default
            # (which bottoms out very thin at high candle counts, prone to
            # anti-aliasing/rounding artifacts that make wicks look
            # off-center) - but not too far, or thick colored edges on
            # adjacent candles start visually bleeding into each other and
            # the whole chart reads as washed-out rather than crisp.
            update_width_config=dict(candle_linewidth=0.7),
        )
        if rsi_period:
            plot_kwargs['panel_ratios'] = (2.2, 1)
        if addplots:
            plot_kwargs['addplot'] = addplots

        # We use returnfig=True to get access to axes for fine-tuning
        fig, axlist = mpf.plot(df, **plot_kwargs)

        if rsi_period:
            # mplfinance returns [main, main-twin, rsi, rsi-twin] with zero
            # gap between the main and RSI panel bboxes by default - close
            # enough that their tick labels overlap. Nudge the two panel
            # groups apart (just enough to clear the labels, not leave dead
            # canvas), then style the RSI axis (0-100 range, 30/50/70
            # oversold/midline/overbought reference lines).
            rsi_ax = next(ax for ax in axlist if ax.get_ylabel() == 'RSI')
            rsi_ax.axhline(70, color='gray', linestyle=':', linewidth=0.8)
            rsi_ax.axhline(50, color='gray', linestyle='-', linewidth=0.6, alpha=0.5)
            rsi_ax.axhline(30, color='gray', linestyle=':', linewidth=0.8)
            rsi_ax.set_ylim(0, 100)
            rsi_ax.set_yticks([0, 30, 50, 70, 100])
            rsi_ax.xaxis.set_visible(False)

            # All of the gap comes out of the RSI panel's top edge, not the
            # main panel's bottom - the main price chart keeps its full
            # nominal height (and the vertical room that would otherwise be
            # dead space between the two panels) instead of splitting the
            # loss with RSI.
            gap = 0.03
            rsi_group = [ax for ax in axlist if ax.get_position().y0 <= rsi_ax.get_position().y0]
            for ax in rsi_group:
                p = ax.get_position()
                ax.set_position([p.x0, p.y0, p.width, p.height - gap])

        # Hide X-axis timestamps explicitly - on the bottom-most panel,
        # whichever that is (RSI if present, otherwise the main panel).
        axlist[0].xaxis.set_visible(False)

        # Save explicitly from figure. dpi=150 (up from matplotlib's default
        # 100) so the wider canvas above renders with enough actual pixels
        # per candle to look crisp, not just spaced out.
        fig.savefig(buf, bbox_inches='tight', pad_inches=0.1, dpi=150)

        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        return img_base64

    except Exception as e:
        logger.error(f"Error generating chart: {e}")
        return None
