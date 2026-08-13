"""
Lean CSV loader for the seed historical data (data_seed/XAUUSD_M1.csv,
XAUUSD_5M_clean.csv). Only handles what the replay harness needs: load, filter
by date range, and resample M1 up to M5/H1 for the sliding window's other tiers.
"""

import pandas as pd


def load_m1_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df['timestamp'] = pd.to_datetime(df['Date'].astype(str) + ' ' + df['Timestamp'], format='%Y%m%d %H:%M:%S')
    df = df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    return df.sort_values('timestamp').reset_index(drop=True)


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """rule: pandas offset alias, e.g. '5min' or '1h'."""
    d = df.set_index('timestamp')
    agg = d.resample(rule).agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'})
    agg = agg.dropna(subset=['open', 'high', 'low', 'close'])
    return agg.reset_index()


class M1SliceIndex:
    """Wraps a full M1 DataFrame with searchsorted-based slicing so repeated
    "give me the window ending at time T" / "give me the N candles after T"
    queries during a multi-hundred-event backtest don't each do an O(n)
    boolean scan over a multi-million-row frame."""

    def __init__(self, m1_df: pd.DataFrame):
        self.df = m1_df
        self._timestamps = m1_df['timestamp'].values

    def window_ending_at(self, end_time, lookback_hours: int) -> pd.DataFrame:
        import numpy as np
        start_time = end_time - pd.Timedelta(hours=lookback_hours)
        start_idx = self._timestamps.searchsorted(np.datetime64(start_time), side='right')
        end_idx = self._timestamps.searchsorted(np.datetime64(end_time), side='right')
        return self.df.iloc[start_idx:end_idx]

    def path_after(self, start_time, max_rows: int = 500) -> pd.DataFrame:
        import numpy as np
        start_idx = self._timestamps.searchsorted(np.datetime64(start_time), side='right')
        return self.df.iloc[start_idx:start_idx + max_rows]
