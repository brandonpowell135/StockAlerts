import discord
from discord.ext import commands, tasks
import yfinance as yf
import os
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

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

# Bot setup for stock alerts
def setup_stock_alerts(bot, CHANNEL_ID):
    global alerts
    alerts = load_alerts_from_file()

    # Command to Set Alert Price 
    @bot.tree.command(name="setalertprice", description="Set a price for a stock to drop to")
    async def setalertprice(interaction: discord.Interaction, ticker: str, target_price: str):
        await interaction.response.defer()  # This defers the response so the interaction doesn't time out.
        
        global alerts
        target_price = float(target_price)
        stock_data = get_stock_data(ticker)

        if stock_data:
            alerts.append({"user_id": interaction.user.id, "ticker": ticker, "target_price": target_price})
            save_alerts_to_file()
            await interaction.followup.send(f"Alert set for **{ticker}** at **{target_price}**")
        else:
            await interaction.followup.send(f"Invalid ticker: **{ticker}**.")

    # Command to Set Alert Percent
    @bot.tree.command(name="setalertpercent", description="Set a percent for a stock to drop")
    async def setalertpercent(interaction: discord.Interaction, ticker: str, target_percent: str):
        await interaction.response.defer()  # This defers the response so the interaction doesn't time out.

        target_percent = float(target_percent)
        stock_data = get_stock_data(ticker)

        if stock_data:
            alerts.append({"user_id": interaction.user.id, "ticker": ticker, "target_percent": target_percent})
            save_alerts_to_file()
            await interaction.followup.send(f"Alert set for **{ticker}** at a **{target_percent}**% drop")
        else:
            await interaction.followup.send(f"Invalid ticker: **{ticker}**.")

    # Command to Get all alerts for users
    @bot.tree.command(name="myalerts", description="See all of your alerts")
    async def myalerts(interaction: discord.Interaction):
        user_alerts = [alert for alert in alerts if alert["user_id"] == interaction.user.id]
        if user_alerts:
            response = "\n".join(
                [f"**{alert['ticker'].upper()}** at $**{alert['target_price']}**" for alert in user_alerts if 'target_price' in alert]
                +
                [f"**{alert['ticker'].upper()}** at **{alert['target_percent']}**%" for alert in user_alerts if 'target_percent' in alert]
            )
            await interaction.response.send_message(f"Your alerts:\n{response}")
        else:
            await interaction.response.send_message("You have no alerts set.")

    # Command to remove all alerts
    @bot.tree.command(name="removealerts", description="Remove all your alerts")
    async def removealerts(interaction: discord.Interaction):
        global alerts
        alerts = [alert for alert in alerts if alert["user_id"] != interaction.user.id]
        save_alerts_to_file()
        await interaction.response.send_message("All your alerts have been removed.")

    # Alert Manager
    @tasks.loop(minutes=1)  # Check every minute
    async def check_alerts():
        global alerts
        for alert in alerts[:]:  # Iterate over a copy of the alerts list
            stock_data = get_stock_data(alert["ticker"])

            if stock_data:
                current_price = stock_data['current_price']
                prev_close_price = stock_data['prev_close_price']
                target_price = alert.get('target_price')
                target_percent = alert.get('target_percent')

                # Check if price or percent target is hit
                if target_price is not None and current_price <= target_price:
                    channel = bot.get_channel(CHANNEL_ID)
                    user = await bot.fetch_user(alert["user_id"])
                    await channel.send(f"{user.mention} Alert: {alert['ticker']} has hit your target price of {alert['target_price']}")
                    alerts.remove(alert)

                if target_percent is not None:
                    percent_drop = percent_calc(prev_close_price, current_price)
                    if percent_drop <= target_percent:
                        channel = bot.get_channel(CHANNEL_ID)
                        user = await bot.fetch_user(alert["user_id"])
                        await channel.send(f"{user.mention} Alert: {alert['ticker']} has hit your target percent of {alert['target_percent']} with a drop of {percent_drop:.2f}%")
                        #alerts.remove(alert)

    # Start the check_alerts task when the bot is ready
    @bot.event
    async def on_ready():
        print(f"Bot is ready as {bot.user}")
        if not check_alerts.is_running():
            check_alerts.start()
