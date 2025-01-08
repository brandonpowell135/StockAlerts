import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

# Function to calculate daily returns and mimic UPRO
def calculate_upro_mimic(ticker, start_date, end_date):
    # Download SPY historical data

    GSPC_data = yf.download(ticker, start=start_date, end=end_date)
    # Calculate daily returns for SPY
    GSPC_data["Daily Return"] = GSPC_data["Close"].pct_change()
    # Mimic UPRO (3x SPY's daily return)
    GSPC_data["UPRO Mimic"] = GSPC_data["Daily Return"] * 3

    UPRO_data = yf.download("UPRO", start=start_date, end=end_date)
    # Calculate daily returns for SPY
    UPRO_data["Daily Return"] = UPRO_data["Close"].pct_change()

    # Combine SPY and UPRO data
    combined_data = pd.DataFrame({
        "S&P Daily Return": GSPC_data["Daily Return"],
        "UPRO Mimic Daily Return": GSPC_data["UPRO Mimic"],
        "UPRO Actual Daily Return": UPRO_data["Daily Return"]

    })

    # Add cumulative returns for all three, starting with a value of 100
    initial_value = 100
    combined_data["SPY Cumulative"] = (1 + combined_data["S&P Daily Return"]).cumprod() * initial_value
    combined_data["UPRO Mimic Cumulative"] = (1 - 0.00015 + combined_data["UPRO Mimic Daily Return"]).cumprod() * initial_value

    return combined_data

# Specify the time range
start_date = "2018-01-01"
end_date = "2020-12-31"
ticker = "^GSPC"

weekly_investment=100
spy_allocation=0.7
upro_allocation=0.3

# Calculate and save results
upro_data = calculate_upro_mimic(ticker=ticker, start_date=start_date, end_date=end_date)

# Save to a CSV file
upro_data.to_csv("upro_mimic_with_profile.csv")

