import yfinance as yf
import pandas as pd

# Set parameters
ticker_symbol = "TQQQ"
investment_per_entry = 100
threshold = -0.10  # 10% drop
start_date = "2020-01-01"  # Starting date for data, adjust as needed

# Fetch historical data
data = yf.download(ticker_symbol, start=start_date)

# Calculate daily percentage change
data["Daily Change %"] = data["Adj Close"].pct_change()

# Identify days with 10% or more drop
drop_days = data[data["Daily Change %"] <= threshold]

# Initialize counters
total_invested = 0.0
total_shares = 0.0

# Calculate entries and average cost
for index, row in drop_days.iterrows():
    shares_bought = investment_per_entry / row["Adj Close"]
    total_shares += shares_bought
    total_invested += investment_per_entry
    
    # Format the drop percentage
    drop_percentage = row["Daily Change %"].item() * 100  # Convert to scalar value and percentage
    print(f"Date: {index.date()}, Drop: {drop_percentage:.2f}%")

# Ensure total_shares is a single number by converting to a float explicitly
total_shares = float(total_shares.iloc[0]) if isinstance(total_shares, pd.Series) else float(total_shares)

# Calculate average cost safely
average_cost = total_invested / total_shares if total_shares > 0 else 0

print(f"\nNumber of Entries: {len(drop_days)}")
print(f"Total Invested: ${total_invested:.2f}")
print(f"Total Shares Purchased: {total_shares:.4f}")
print(f"Average Cost per Share: ${average_cost:.2f}")
