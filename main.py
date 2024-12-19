import discord
from discord.ext import commands
from dotenv import load_dotenv
import os


from stockalerts import setup_stock_alerts
from portfolio import login_to_robinhood, portfolio_managment
from backtest import backtest
from generalchat import general_commands

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

# Create Discord bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def main():
    #Log in to Robinhood
    logged_in = login_to_robinhood()
    if not login_to_robinhood():
        print("Failed to log in to Robinhood.")

    # Set up bot commands
    setup_stock_alerts(bot, CHANNEL_ID)
    general_commands(bot)
    backtest(bot)

    if logged_in:
        portfolio_managment(bot)
    else:
        print("Portfolio management commands will not be available.")

    # Run bot
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
