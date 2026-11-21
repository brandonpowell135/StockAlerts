import pandas as pd
import pytest

from backtest import run_drop_backtest
from backtest_data import (
    DAILY_EXPENSE,
    calculate_upro_mimic,
    last_trading_day_of_quarter,
    longest_recovery,
    max_drawdown,
    simulate_profile_return,
)


def make_closes(values, start="2024-01-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


# --- /backtest command math -------------------------------------------------
def test_drop_backtest_accepts_positive_or_negative_percent():
    history = pd.DataFrame({"Close": make_closes([100, 90, 95, 85.5, 100])})  # -10%, +5.6%, -10%, +17%
    pos = run_drop_backtest(history, 5)
    neg = run_drop_backtest(history, -5)
    assert pos == neg
    assert pos["entries"] == 2
    assert pos["total_invested"] == 200
    assert pos["total_shares"] == pytest.approx(100 / 90 + 100 / 85.5)
    assert pos["hold_value"] == pytest.approx(200)  # bought at 100, now 100


def test_drop_backtest_no_qualifying_days():
    history = pd.DataFrame({"Close": make_closes([100, 101, 102])})
    assert run_drop_backtest(history, 3) is None


# --- backtest_data.py -------------------------------------------------------
def test_upro_mimic_tracks_3x_and_is_not_inverted():
    data = calculate_upro_mimic(make_closes([100, 101, 102.01]))  # +1% twice
    assert data["UPRO Mimic Daily Return"].iloc[1] == pytest.approx(0.03 - DAILY_EXPENSE)
    # Cumulative goes UP when the index goes up (old code used 1 - r and went down).
    assert data["UPRO Mimic Cumulative"].iloc[-1] > 100
    assert data["UPRO Mimic Cumulative"].iloc[-1] == pytest.approx(100 * (1.03 - DAILY_EXPENSE) ** 2)


def test_quarter_end_uses_last_trading_day():
    # 2024-03-29 (Fri) is the last trading day of Q1; Mar 30-31 are a weekend.
    index = pd.bdate_range("2024-03-25", "2024-04-05")
    flags = pd.Series(last_trading_day_of_quarter(index), index=index)
    assert list(flags[flags].index) == [pd.Timestamp("2024-03-29")]


def test_data_ending_mid_quarter_is_not_a_rebalance_day():
    index = pd.bdate_range("2024-11-01", "2024-11-29")
    assert not last_trading_day_of_quarter(index).any()


def test_drawdown_and_recovery():
    values = make_closes([100, 120, 90, 100, 125, 110])
    assert max_drawdown(values) == pytest.approx(-25)
    # Underwater from Wed (90) until Fri (125) = 2 days; the open drawdown on the last day is shorter.
    assert longest_recovery(values).days == 2


def test_simulation_contributes_weekly_and_flat_market_keeps_value():
    closes = make_closes([100] * 15)  # three flat weeks
    data = simulate_profile_return(calculate_upro_mimic(closes), 100, 0.7, 0.3)
    assert data["Contributions"].iloc[-1] == 300
    # Flat index, so only UPRO's expense ratio drags the value below contributions.
    assert data["S&P Portfolio Value"].iloc[-1] == pytest.approx(300)
    assert data["UPRO Portfolio Value"].iloc[-1] < 300
    assert data["Profile Portfolio Value"].iloc[-1] == pytest.approx(
        data["S&P Portfolio Normal"].iloc[-1] + data["UPRO Portfolio Normal"].iloc[-1]
    )
