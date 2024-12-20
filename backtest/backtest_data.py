import yfinance as yf
import pandas as pd

# Function to calculate daily returns and mimic UPRO
def calculate_upro_mimic(ticker="SPY", upro_ticker="UPRO", start_date="2020-01-01", end_date="2024-12-31"):
    # Download SPY historical data
    GSPC_data = yf.download(ticker, start=start_date, end=end_date)
    
    # Download UPRO historical data
    upro_data = yf.download(upro_ticker, start=start_date, end=end_date)

    # Calculate daily returns for SPY
    GSPC_data["Daily Return"] = GSPC_data["Adj Close"].pct_change()

    # Mimic UPRO (3x SPY's daily return)
    GSPC_data["UPRO Mimic"] = GSPC_data["Daily Return"] * 3

    # Calculate daily returns for UPRO
    upro_data["Daily Return"] = upro_data["Adj Close"].pct_change()

    # Align indices to ensure compatibility
    upro_data = upro_data.reindex(GSPC_data.index)

    # Combine SPY and UPRO data
    combined_data = pd.DataFrame({
        "S&P Daily Return": GSPC_data["Daily Return"],
        "UPRO Mimic": GSPC_data["UPRO Mimic"],
        "UPRO Daily Return": upro_data["Daily Return"]
    })

    return combined_data

# Specify the time range
start_date = "2010-01-01"
end_date = "2024-12-31"

# Calculate and save results
upro_data = calculate_upro_mimic(start_date=start_date, end_date=end_date)

# Save to a CSV file
upro_data.to_csv("upro_mimic_spy.csv")

print("UPRO mimic data has been saved to 'upro_mimic.csv'.")
