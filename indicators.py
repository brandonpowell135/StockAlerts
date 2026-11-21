"""Technical indicators computed from a Series of daily closes. Pure functions, no I/O."""
import math

import pandas as pd

RSI_PERIOD = 14


def sma(closes, window):
    """Simple moving average; NaN until `window` closes are available."""
    return closes.rolling(window=window, min_periods=window).mean()


def _wilder_rsi_value(avg_gain, avg_loss):
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def rsi(closes, period=RSI_PERIOD):
    """Relative Strength Index with Wilder's smoothing, matching TradingView/StockCharts.

    The first average is a simple mean of the first `period` changes; after that each
    average is smoothed as (prev * (period - 1) + current) / period.
    """
    values = [float(v) for v in closes]
    result = [math.nan] * len(values)
    if len(values) <= period:
        return pd.Series(result, index=closes.index)

    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(c, 0.0) for c in changes]
    losses = [max(-c, 0.0) for c in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    result[period] = _wilder_rsi_value(avg_gain, avg_loss)
    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        result[i + 1] = _wilder_rsi_value(avg_gain, avg_loss)
    return pd.Series(result, index=closes.index)


def crossed(prev, curr, level, direction):
    """True if the value moved across `level` between two readings in the given direction.

    "above": was at or below the level, now above it.
    "below": was at or above the level, now below it.
    """
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in (prev, curr, level)):
        return False
    if direction == "above":
        return prev <= level < curr
    if direction == "below":
        return prev >= level > curr
    raise ValueError(f"direction must be 'above' or 'below', got {direction!r}")


def last_two(series):
    """The previous and latest values of a Series, or (None, None) if it is too short."""
    clean = series.dropna()
    if len(clean) < 2:
        return None, None
    return float(clean.iloc[-2]), float(clean.iloc[-1])


def sma_cross(closes, window, direction):
    """Did the latest close cross its `window`-day SMA in `direction`?

    Returns (crossed, sma_value). Compares price minus SMA against 0 so a moving SMA works.
    """
    if len(closes) < window + 1:
        return False, None
    average = sma(closes, window)
    diff = pd.Series(closes.values - average.values, index=closes.index)
    prev_diff, curr_diff = last_two(diff)
    return crossed(prev_diff, curr_diff, 0.0, direction), float(average.iloc[-1])


def rsi_cross(closes, threshold, direction, period=RSI_PERIOD):
    """Did RSI cross `threshold` in `direction` on the latest close? Returns (crossed, rsi_value)."""
    values = rsi(closes, period)
    prev_rsi, curr_rsi = last_two(values)
    return crossed(prev_rsi, curr_rsi, threshold, direction), curr_rsi
