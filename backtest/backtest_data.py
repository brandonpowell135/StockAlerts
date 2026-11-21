"""Backtest a weekly-contribution portfolio split between an index and a simulated 3x ETF (UPRO).

Run directly: python backtest/backtest_data.py
Writes upro_mimic_with_profile.csv and cumulative_returns_and_profile_graph.png.
"""
import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252
LEVERAGE = 3
UPRO_EXPENSE_RATIO = 0.0091  # 0.91% per year
DAILY_EXPENSE = UPRO_EXPENSE_RATIO / TRADING_DAYS_PER_YEAR


def download_closes(ticker, start_date, end_date):
    import yfinance as yf

    data = yf.download(ticker, start=start_date, end=end_date, auto_adjust=True, progress=False)
    if isinstance(data.columns, pd.MultiIndex):  # newer yfinance returns (field, ticker) columns
        data.columns = data.columns.get_level_values(0)
    if data.empty:
        raise ValueError(f"No data returned for {ticker} between {start_date} and {end_date}")
    return data["Close"]


def calculate_upro_mimic(closes):
    """Daily returns for the index and a 3x leveraged version net of its expense ratio."""
    index_return = closes.pct_change().fillna(0.0)
    upro_return = index_return * LEVERAGE - DAILY_EXPENSE
    upro_return.iloc[0] = 0.0

    initial_value = 100
    combined = pd.DataFrame(
        {
            "S&P Daily Return": index_return,
            "UPRO Mimic Daily Return": upro_return,
        }
    )
    combined.index = pd.to_datetime(combined.index)
    combined["SPY Cumulative"] = (1 + index_return).cumprod() * initial_value
    combined["UPRO Mimic Cumulative"] = (1 + upro_return).cumprod() * initial_value
    return combined


def first_trading_day_of_week(index):
    weeks = index.to_period("W")
    return ~weeks.duplicated()


def last_trading_day_of_quarter(index):
    quarters = index.to_period("Q")
    is_last = ~quarters.duplicated(keep="last")
    # The final row is only a quarter end if the data actually reaches the quarter's end
    # (i.e. the next business day falls in a new quarter), not just where the data stops.
    if len(index) and (index[-1] + pd.offsets.BDay(1)).to_period("Q") == quarters[-1]:
        is_last[-1] = False
    return is_last


def max_drawdown(values):
    """Largest peak-to-trough decline as a negative percentage."""
    running_peak = values.cummax()
    return float(((values - running_peak) / running_peak).min() * 100)


def longest_recovery(values):
    """Longest time spent below a previous peak (still-open drawdowns count up to the last date)."""
    running_peak = values.cummax()
    underwater = values < running_peak
    longest = pd.Timedelta(0)
    start = None
    for date, below in underwater.items():
        if below and start is None:
            start = date
        elif not below and start is not None:
            longest = max(longest, date - start)
            start = None
    if start is not None:
        longest = max(longest, values.index[-1] - start)
    return longest


def sharpe_ratio(daily_returns, risk_free_rate=0.0):
    excess = daily_returns - risk_free_rate / TRADING_DAYS_PER_YEAR
    std = excess.std()
    if not std or np.isnan(std):
        return 0.0
    return float(excess.mean() / std * np.sqrt(TRADING_DAYS_PER_YEAR))


def simulate_profile_return(combined_data, weekly_investment, spy_allocation, upro_allocation):
    """Invest weekly into three portfolios: all-index, all-UPRO, and a rebalanced mix.

    Contributions are bought at the close of the first trading day of each week, so
    they start earning the next day. The mix is rebalanced on the last trading day
    of each quarter.
    """
    data = combined_data.copy()
    data.index = pd.to_datetime(data.index)
    data["Contribution Day"] = first_trading_day_of_week(data.index)
    data["Quarter End"] = last_trading_day_of_quarter(data.index)

    spy_only = upro_only = mix_spy = mix_upro = contributions = 0.0
    spy_values, upro_values, mix_spy_values, mix_upro_values = [], [], [], []
    mix_values, mix_daily_returns, contribution_values = [], [], []

    for date, row in data.iterrows():
        r_spy = row["S&P Daily Return"]
        r_upro = row["UPRO Mimic Daily Return"]

        # 1. Apply today's return to what was held overnight.
        mix_before = mix_spy + mix_upro
        spy_only *= 1 + r_spy
        upro_only *= 1 + r_upro
        mix_spy *= 1 + r_spy
        mix_upro *= 1 + r_upro
        mix_daily_returns.append((mix_spy + mix_upro) / mix_before - 1 if mix_before else 0.0)

        # 2. Add this week's contribution at the close.
        if row["Contribution Day"]:
            spy_only += weekly_investment
            upro_only += weekly_investment
            mix_spy += weekly_investment * spy_allocation
            mix_upro += weekly_investment * upro_allocation
            contributions += weekly_investment

        # 3. Rebalance the mix back to target weights.
        if row["Quarter End"]:
            total = mix_spy + mix_upro
            mix_spy, mix_upro = total * spy_allocation, total * upro_allocation

        spy_values.append(spy_only)
        upro_values.append(upro_only)
        mix_spy_values.append(mix_spy)
        mix_upro_values.append(mix_upro)
        mix_values.append(mix_spy + mix_upro)
        contribution_values.append(contributions)

    data["S&P Portfolio Value"] = spy_values
    data["UPRO Portfolio Value"] = upro_values
    data["S&P Portfolio Normal"] = mix_spy_values
    data["UPRO Portfolio Normal"] = mix_upro_values
    data["Profile Portfolio Value"] = mix_values
    data["Profile Daily Return"] = mix_daily_returns
    data["Contributions"] = contribution_values
    # Time-weighted index for the mix, so drawdowns aren't masked by new contributions.
    data["Profile Cumulative"] = (1 + data["Profile Daily Return"]).cumprod() * 100

    final_contributions = contributions
    for column, value_column in [
        ("S&P_return", "S&P Portfolio Value"),
        ("UPRO_mimic_return", "UPRO Portfolio Value"),
        ("Profile_return", "Profile Portfolio Value"),
    ]:
        data[column] = (data[value_column].iloc[-1] - final_contributions) / final_contributions * 100

    return data


def summarize(data):
    series = {
        "S&P": (data["SPY Cumulative"], data["S&P Daily Return"]),
        "UPRO Mimic": (data["UPRO Mimic Cumulative"], data["UPRO Mimic Daily Return"]),
        "Profile Portfolio": (data["Profile Cumulative"], data["Profile Daily Return"]),
    }
    return {
        name: {
            "max_drawdown": max_drawdown(values),
            "longest_recovery_days": longest_recovery(values).days,
            "sharpe": sharpe_ratio(returns.iloc[1:]),
        }
        for name, (values, returns) in series.items()
    }


def plot_results(data, metrics, output_path):
    import matplotlib.pyplot as plt

    plt.figure(figsize=(12, 6))
    plt.plot(data.index, data["S&P Portfolio Value"],
             label=f"S&P Return {data['S&P_return'].iloc[-1]:.2f}%", color="blue")
    plt.plot(data.index, data["UPRO Portfolio Value"],
             label=f"UPRO Mimic Return {data['UPRO_mimic_return'].iloc[-1]:.2f}%", color="orange")
    plt.plot(data.index, data["Profile Portfolio Value"],
             label=f"Profile Portfolio Return {data['Profile_return'].iloc[-1]:.2f}%", color="green")
    plt.plot(data.index, data["Contributions"], label="Contributions", color="purple")
    plt.title("Weekly Contributions: S&P vs UPRO Mimic vs Rebalanced Profile")
    plt.xlabel("Date")
    plt.ylabel("Portfolio Value")
    plt.legend()
    plt.grid()

    table_data = pd.DataFrame(
        {
            "": ["Max Drawdown", "Longest Underwater", "Sharpe Ratio (rf=0)"],
            **{
                name: [f"{m['max_drawdown']:.2f}%", f"{m['longest_recovery_days']} days", f"{m['sharpe']:.2f}"]
                for name, m in metrics.items()
            },
        }
    )
    table = plt.table(cellText=table_data.values, colLabels=table_data.columns,
                      cellLoc="center", bbox=[0.0, -0.45, 1.0, 0.3])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    plt.subplots_adjust(bottom=0.4)
    plt.savefig(output_path, bbox_inches="tight")
    return plt


def main():
    start_date = "2020-01-01"
    end_date = "2020-12-01"
    ticker = "^GSPC"  # price index (no dividends); use "SPY" for total return

    weekly_investment = 100
    spy_allocation = 0.7
    upro_allocation = 0.3

    closes = download_closes(ticker, start_date, end_date)
    data = calculate_upro_mimic(closes)
    data = simulate_profile_return(data, weekly_investment, spy_allocation, upro_allocation)
    metrics = summarize(data)

    data.to_csv("upro_mimic_with_profile.csv")
    plt = plot_results(data, metrics, "cumulative_returns_and_profile_graph.png")

    for name, m in metrics.items():
        print(f"{name}: max drawdown {m['max_drawdown']:.2f}%, "
              f"longest underwater {m['longest_recovery_days']} days, Sharpe {m['sharpe']:.2f}")
    print("Data saved to 'upro_mimic_with_profile.csv'; graph saved to "
          "'cumulative_returns_and_profile_graph.png'.")
    plt.show()


if __name__ == "__main__":
    main()
