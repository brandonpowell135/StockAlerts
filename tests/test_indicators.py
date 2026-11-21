import math

import pandas as pd
import pytest

from indicators import crossed, rsi, rsi_cross, sma, sma_cross

# Wilder's worked example as published by StockCharts (their table rounds intermediate
# values, so we allow a small tolerance).
WILDER_CLOSES = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
                 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64]
WILDER_RSI = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97]


def test_sma():
    result = sma(pd.Series([1, 2, 3, 4, 5], dtype=float), 3)
    assert math.isnan(result.iloc[1])
    assert result.tolist()[2:] == [2.0, 3.0, 4.0]


def test_rsi_matches_wilder_example():
    values = rsi(pd.Series(WILDER_CLOSES)).tolist()
    assert all(math.isnan(v) for v in values[:14])
    assert values[14:] == pytest.approx(WILDER_RSI, abs=0.1)


def test_rsi_edge_cases():
    assert rsi(pd.Series(range(1, 17), dtype=float)).iloc[-1] == 100.0  # only gains
    assert rsi(pd.Series(range(16, 0, -1), dtype=float)).iloc[-1] == 0.0  # only losses
    assert rsi(pd.Series([5.0] * 16)).iloc[-1] == 50.0  # flat
    assert rsi(pd.Series([1.0, 2.0])).isna().all()  # too short


@pytest.mark.parametrize(
    "prev, curr, level, direction, expected",
    [
        (29, 31, 30, "above", True),
        (30, 31, 30, "above", True),   # touching then crossing counts
        (31, 32, 30, "above", False),  # already above
        (31, 29, 30, "below", True),
        (29, 28, 30, "below", False),  # already below (no daily repeats)
        (31, 30, 30, "below", False),  # touching isn't crossing
        (float("nan"), 31, 30, "above", False),
        (None, 31, 30, "above", False),
    ],
)
def test_crossed(prev, curr, level, direction, expected):
    assert crossed(prev, curr, level, direction) is expected


def test_crossed_rejects_bad_direction():
    with pytest.raises(ValueError):
        crossed(1, 2, 1.5, "sideways")


def test_sma_cross():
    closes = pd.Series([100.0] * 20 + [99.0, 105.0])  # dips below the 20-day SMA, then pops above
    did_cross, average = sma_cross(closes, 20, "above")
    assert did_cross
    assert average == pytest.approx((18 * 100 + 99 + 105) / 20)
    assert not sma_cross(closes, 20, "below")[0]
    assert sma_cross(closes[:20], 20, "above") == (False, None)  # not enough history


def test_rsi_cross():
    falling = pd.Series([100.0 + i for i in range(20)] + [90.0, 80.0, 70.0])
    rsis = rsi(falling)
    # Find where RSI dropped through 30 and check rsi_cross agrees on that bar only.
    for end in range(16, len(falling) + 1):
        window = falling[:end]
        prev, curr = rsis.iloc[end - 2], rsis.iloc[end - 1]
        assert rsi_cross(window, 30, "below")[0] == (prev >= 30 > curr)
    assert any(rsi_cross(falling[:end], 30, "below")[0] for end in range(16, len(falling) + 1))
