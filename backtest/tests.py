import yfinance as yf
import pandas as pd

# Function to calculate daily returns and mimic UPRO
def calculate_upro_mimic(ticker="SPY", upro_ticker="UPRO", start_date="2020-01-01", end_date="2024-12-31"):
    # Download SPY historical data
    spy_data = yf.download(ticker, start=start_date, end=end_date)
    
    # Download UPRO historical data
    upro_data = yf.download(upro_ticker, start=start_date, end=end_date)

    # Calculate daily returns based on Adj Close
    spy_data["Daily Return (Adj Close)"] = spy_data["Adj Close"].pct_change()
    upro_data["Daily Return (Adj Close)"] = upro_data["Adj Close"].pct_change()

    # Calculate intraday returns based on Open and Close prices
    spy_data["Intraday Return"] = (spy_data["Close"] - spy_data["Open"]) / spy_data["Open"]
    upro_data["Intraday Return"] = (upro_data["Close"] - upro_data["Open"]) / upro_data["Open"]

    # Mimic UPRO (3x SPY's daily return based on Adj Close)
    spy_data["UPRO Mimic (Adj Close)"] = spy_data["Daily Return (Adj Close)"] * 3

    # Align indices to ensure compatibility
    upro_data = upro_data.reindex(spy_data.index)

    # Combine SPY and UPRO data
    combined_data = pd.DataFrame({
        "SPY Daily Return (Adj Close)": spy_data["Daily Return (Adj Close)"],
        "SPY Intraday Return": spy_data["Intraday Return"],
        "UPRO Mimic (Adj Close)": spy_data["UPRO Mimic (Adj Close)"],
        "UPRO Daily Return (Adj Close)": upro_data["Daily Return (Adj Close)"],
        "UPRO Intraday Return": upro_data["Intraday Return"]
    })

    return combined_data

# Specify the time range
start_date = "2010-01-01"
end_date = "2024-12-31"

# Calculate and save results
upro_data = calculate_upro_mimic(start_date=start_date, end_date=end_date)

# Save to a CSV file
upro_data.to_csv("upro_mimic_with_intraday.csv")

print("UPRO mimic data with intraday returns has been saved to 'upro_mimic_with_intraday.csv'.")
