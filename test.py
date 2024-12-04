import discord
from discord.ext import commands, tasks
from discord import app_commands
import yfinance as yf
import os
from dotenv import load_dotenv
import json
import pandas as pd
import datetime


# Load environment variables from a .env file
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
channel_ID = 1304872669740667000

# Create a bot instance with a command prefix
intents = discord.Intents.default()
intents.message_content = True  # Make sure to allow reading messages
bot = commands.Bot(command_prefix="!", intents=intents)

# Save alerts to file
def save_alerts_to_file():
    with open("alerts.json", "w") as file:
        json.dump(alerts, file)

# Load file
def load_alerts_from_file():
    if os.path.exists("alerts.json"):
        with open("alerts.json", "r") as file:
            return json.load(file)
    return []

# Load alerts on start up
alerts = load_alerts_from_file()

# Function to get stock data
def get_stock_data(ticker):
    stock = yf.Ticker(ticker)
    data = stock.history(period="5d")
    if not data.empty:
        open_price = data['Open'].iloc[0]
        close_price = data['Close'].iloc[0]
        current_price = data['Close'].iloc[-1]
        prev_close_price = data['Close'].iloc[-2]
        return {
            "ticker": ticker,
            "open_price": open_price,
            "close_price": close_price,
            "current_price": current_price,
            "prev_close_price": prev_close_price
        }
    else:
        return None

# Function to calculate percent drop
def percent_calc(prev_close_price, current_price):
    return ((current_price - prev_close_price) / prev_close_price) * 100

# Bot log in
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} ')
    await bot.tree.sync()  # Sync the slash commands with Discord
    check_alerts.start()

# Commend to Set Alert Price 
@bot.tree.command(name="setalertprice", description="Set a price for a stock to drop to")
async def setalertprice(interaction: discord.Interaction, ticker: str, target_price: str):
    target_price = float(target_price)
    stock_data = get_stock_data(ticker)

    if stock_data:
        alerts.append({"user_id": interaction.user.id, "ticker": ticker, "target_price": target_price})
        save_alerts_to_file()
        await interaction.response.send_message(f"Alert set for {ticker} at {target_price}")
    else:
        await interaction.response.send_message(f"Invalid ticker: {ticker}.")

# Command to Set Alert Percent
@bot.tree.command(name="setalertpercent", description="Set a percent for a stock to drop")
async def setalertpercent(interaction: discord.Interaction, ticker: str, target_percent: str):
    target_percent = float(target_percent)
    stock_data = get_stock_data(ticker)

    if stock_data:
        alerts.append({"user_id": interaction.user.id, "ticker": ticker, "target_percent": target_percent})
        save_alerts_to_file()
        await interaction.response.send_message(f"Alert set for {ticker} at a {target_percent}% drop")
    else:
        await interaction.response.send_message(f"Invalid ticker: {ticker}.")

# Command to Get all alerts for users
@bot.tree.command(name="myalerts", description="See all of your alerts")
async def myalerts(interaction: discord.Interaction):
    alerts = load_alerts_from_file()
    user_alerts = [alert for alert in alerts if alert["user_id"] == interaction.user.id]
    if user_alerts:
        response = "\n".join(
            [f"{alert['ticker'].upper()} at ${alert['target_price']}" for alert in user_alerts if 'target_price' in alert]
            +
            [f"{alert['ticker'].upper()} at {alert['target_percent']}%" for alert in user_alerts if 'target_percent' in alert]
        )
        await interaction.response.send_message(f"Your alerts:\n{response}")
    else:
        await interaction.response.send_message("You have no alerts set.")

# Command to remove alert
@bot.tree.command(name="removealerts", description="Remove all your alerts")
async def removealerts(interaction: discord.Interaction):
    global alerts
    alerts = [alert for alert in alerts if alert["user_id"] != interaction.user.id]
    save_alerts_to_file()
    await interaction.response.send_message("All your alerts have been removed.")


# Alert Manager
@tasks.loop(minutes=1) # Checks every min
async def check_alerts():
    for alert in alerts[:]: # Iterates over a copy of the alerts list
        stock_data = get_stock_data(alert["ticker"])

        if stock_data:
            current_price = stock_data['current_price']
            open_price = stock_data['open_price']
            prev_close_price = stock_data['prev_close_price']
            target_price = alert.get('target_price')
            target_percent = alert.get('target_percent')

            if target_price is not None and current_price <= target_price:
                channel = bot.get_channel(channel_ID)
                user = await bot.fetch_user(alert["user_id"])
                await channel.send(f"{user.mention} Alert: {alert['ticker']} has hit your target price of {alert['target_price']}")
                alerts.remove(alert)

            if target_percent is not None:
                percent_drop = percent_calc(prev_close_price, current_price)
                if percent_drop <= target_percent:
                    channel = bot.get_channel(channel_ID)
                    user = await bot.fetch_user(alert["user_id"])
                    await channel.send(f"{user.mention} Alert: {alert['ticker']} has hit your target percent of {alert['target_percent']} with a drop of {percent_drop:.2f}%")  

# Command tto backtest
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

# Run the bot with your token
bot.run(TOKEN)
