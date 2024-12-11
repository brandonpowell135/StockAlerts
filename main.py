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
    if not login_to_robinhood():
        print("Failed to log in to Robinhood.")
        return

    # Set up bot commands
    setup_stock_alerts(bot, CHANNEL_ID)
    general_commands(bot)
    portfolio_managment(bot)
    backtest(bot)

    # Run bot
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
