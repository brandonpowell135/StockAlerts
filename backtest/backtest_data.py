import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

# Function to calculate daily returns and mimic UPRO
def calculate_upro_mimic(ticker, start_date, end_date):
    # Download SPY historical data
    SPY_data = yf.download(ticker, start=start_date, end=end_date)
    # Calculate daily returns for SPY
    SPY_data["Daily Return"] = SPY_data["Adj Close"].pct_change()
    # Mimic UPRO (3x SPY's daily return)
    SPY_data["UPRO Mimic"] = SPY_data["Daily Return"] * 3

    # Combine SPY and UPRO data
    combined_data = pd.DataFrame({
        "S&P Daily Return": SPY_data["Daily Return"],
        "UPRO Mimic Daily Return": SPY_data["UPRO Mimic"],
    })

    # Add cumulative returns for all three, starting with a value of 100
    initial_value = 100
    combined_data["SPY Cumulative"] = (1 + combined_data["S&P Daily Return"]).cumprod() * initial_value
    combined_data["UPRO Mimic Cumulative"] = (1 - 0.00015 + combined_data["UPRO Mimic Daily Return"]).cumprod() * initial_value

    return combined_data

# Function to simulate a portfolio with weekly investments
def simulate_profile_return(combined_data, weekly_investment, spy_allocation, upro_allocation):
    # Initialize portfolio values for SPY and UPRO Mimic
    portfolio_spy = 0
    portfolio_upro = 0
    portfolio_spy_return = 0
    portfolio_upro_return = 0
    portfolio_contributions = 0
    portfolio_value = []
    portfolio_upro_value = []
    portfolio_spy_value = []
    portfolio_spy_normal = []
    portfolio_upro_normal = []
    portfolio_contributions_value = []

    # Add Quarter End column based on the last day of each quarter
    combined_data.index = pd.to_datetime(combined_data.index)

    # Identify the last day of each quarter
    combined_data['Quarter End'] = combined_data.index.isin(
        combined_data[combined_data.index.is_month_end & combined_data.index.month.isin([3, 6, 9, 12])].index
    )

    # Loop through each day in the dataset
    for i in range(len(combined_data)):
        # Weekly investments are added every Monday (or the first day of the dataset)
        if i % 5 == 0:  # Assume a 5-day trading week
            # Split the weekly investment between SPY and UPRO Mimic
            investment_spy = weekly_investment * spy_allocation
            investment_upro = weekly_investment * upro_allocation
            investment_spy_profile = weekly_investment
            investment_upro_profile = weekly_investment

            # Add the investments to the portfolio
            portfolio_spy += investment_spy
            portfolio_upro += investment_upro
            portfolio_spy_return += investment_spy_profile
            portfolio_upro_return += investment_upro_profile
            portfolio_contributions += weekly_investment

        # Apply daily returns to grow the portfolio
        if i > 0:  # Skip the first day (no previous data for returns)
            portfolio_spy = portfolio_spy * (1 + combined_data["S&P Daily Return"].iloc[i])
            portfolio_upro = portfolio_upro * (1 + combined_data["UPRO Mimic Daily Return"].iloc[i])

            portfolio_spy_return = portfolio_spy_return * (1 + combined_data["S&P Daily Return"].iloc[i])
            portfolio_upro_return = portfolio_upro_return * (1 + combined_data["UPRO Mimic Daily Return"].iloc[i])

        # Rebalance at the end of the quarter
        if combined_data["Quarter End"].iloc[i]:
            spy_amount = (portfolio_spy + portfolio_upro) * spy_allocation
            upro_amount = (portfolio_spy + portfolio_upro) * upro_allocation

            portfolio_spy = spy_amount
            portfolio_upro = upro_amount

        # Calculate the total portfolio value and store it
        portfolio_spy_value.append(portfolio_spy_return)
        portfolio_upro_value.append(portfolio_upro_return)

        portfolio_spy_normal.append(portfolio_spy)
        portfolio_upro_normal.append(portfolio_upro)
        portfolio_value.append(portfolio_spy + portfolio_upro)

        portfolio_contributions_value.append(portfolio_contributions)


    # Add the portfolio value to the combined data
    combined_data["SPY Portfolio Value"] = portfolio_spy_value
    combined_data["UPRO Portfolio Value"] = portfolio_upro_value

    combined_data["SPY Portfolio Normal"] = portfolio_spy_normal
    combined_data["UPRO Portfolio Normal"] = portfolio_upro_normal
    combined_data["Profile Portfolio Value"] = portfolio_value
    
    combined_data["Contributions"] = portfolio_contributions_value

    final_contributions = combined_data["Contributions"].iloc[-1]

    combined_data["UPRO_mimic_return"] = ((combined_data["UPRO Portfolio Value"].iloc[-1] - final_contributions) / final_contributions) * 100
    combined_data["SPY_return"] = ((combined_data["SPY Portfolio Value"].iloc[-1] - final_contributions) / final_contributions) * 100
    combined_data["Profile_return"] = ((combined_data["Profile Portfolio Value"].iloc[-1] - final_contributions) / final_contributions) * 100

    return combined_data

# Specify the time range
start_date = "1996-01-01"
end_date = "2020-12-31"
ticker = "SPY"

weekly_investment=100
spy_allocation=0.7
upro_allocation=0.3

# Calculate and save results
upro_data = calculate_upro_mimic(ticker=ticker, start_date=start_date, end_date=end_date)

# Simulate profile return with weekly $100 investment (50% in SPY, 50% in UPRO Mimic)
upro_data = simulate_profile_return(upro_data, weekly_investment=weekly_investment, spy_allocation=spy_allocation, upro_allocation=upro_allocation)

# Save to a CSV file
upro_data.to_csv("upro_mimic_with_profile.csv")

# Plot the cumulative returns
plt.figure(figsize=(12, 6))

plt.plot(upro_data.index,
upro_data["SPY Portfolio Value"], 
label=f"SPY Cumulative Return {upro_data['SPY_return'].iloc[-1]:.2f}%", 
color="blue")

plt.plot(upro_data.index, 
upro_data["UPRO Portfolio Value"], 
label=f"UPRO Mimic Cumulative Return {upro_data['UPRO_mimic_return'].iloc[-1]:.2f}%", 
color="orange")

plt.plot(upro_data.index, 
upro_data["Profile Portfolio Value"], 
label=f"Profile Portfolio Return {upro_data['Profile_return'].iloc[-1]:.2f}%", 
color="green")

plt.plot(upro_data.index, 
upro_data["Contributions"], 
label="Profile Contributions", 
color="purple")

plt.title("Cumulative Returns of SPY, UPRO Mimic, and Profile Portfolio")
plt.xlabel("Date")
plt.ylabel("Portfolio Value")
plt.legend()
plt.grid()
plt.tight_layout()

# Save the graph as a file
plt.savefig("cumulative_returns_and_profile_graph.png")

# Show the graph
plt.show()

print("UPRO mimic data with cumulative returns and profile portfolio has been saved to 'upro_mimic_with_profile.csv'.")
print("Graph has been saved to 'cumulative_returns_and_profile_graph.png'.")
