import pandas as pd
import discord
import yfinance as yf

from stockalerts import get_stock_data, percent_calc


def backtest(bot):
    # Command to backtest
    @bot.tree.command(name="backtest", description="Backtest your strategies")
    async def backtest(interaction: discord.Interaction, ticker: str, target_percent: str, start_date: str):
        # Parse inputs
        target_percent = float(target_percent)
        
        # Fetch current stock data for the latest price
        current_stock_data = get_stock_data(ticker)
        if not current_stock_data:
            await interaction.response.send_message(f"Invalid ticker: {ticker}.")
            return

        current_price = current_stock_data["current_price"]

        # Fetch historical data for backtesting
        historical_data = yf.Ticker(ticker).history(start=start_date, period="max")

        if historical_data.empty:
            await interaction.response.send_message(f"No data found for {ticker} starting from {start_date}.")
            return

        # Calculate daily percentage changes and find significant drops
        historical_data["Daily Change %"] = historical_data["Close"].pct_change() * 100
        drop_days = historical_data[historical_data["Daily Change %"] <= target_percent]

        if drop_days.empty:
            await interaction.response.send_message(f"No drops of {target_percent}% or more found for {ticker}.")
            return

        # Simulate investment strategy
        investment_per_entry = 100  # Example: $100 per drop
        total_invested = 0.0
        total_shares = 0.0

        for _, row in drop_days.iterrows():
            shares_bought = investment_per_entry / row["Close"]
            total_shares += shares_bought
            total_invested += investment_per_entry

        # Calculate results
        average_cost = total_invested / total_shares if total_shares > 0 else 0
        percent_gain = percent_calc(average_cost, current_price)

        # Send results back to the user
        await interaction.response.send_message(
            f"Backtesting {ticker} strategy for drops of {target_percent}% or more:\n"
            f"- Number of Entries: {len(drop_days)}\n"
            f"- Total Invested: ${total_invested:.2f}\n"
            f"- Total Shares Purchased: {total_shares:.4f}\n"
            f"- Average Cost per Share: ${average_cost:.2f}\n"
            f"- Current Price: ${current_price:.2f}\n"
            f"- Percent Gain/Loss: {percent_gain:.2f}%"
        )