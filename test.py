import yfinance as yf
import os 
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks

# Load environment variables from a .env file
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
channel_ID = 1304872669740667000

# Create a bot instance with a command prefix
intents = discord.Intents.default()
intents.message_content = True  # Make sure to allow reading messages
bot = commands.Bot(command_prefix="!", intents=intents)

class User():
    def __init__(self,username):
        self.username = username
        pass

def get_stock_data(ticker):
    stock = yf.Ticker(ticker)
    data = stock.history(period="1d")
    if not data.empty:
        open_price = data['Open'].iloc[0]
        close_price = data['Close'].iloc[0]
        current_price = data['Close'].iloc[-1]
        return {
            "ticker": ticker,
            "open_price": open_price,
            "close_price": close_price,
            "current_price": current_price
        }
    else:
        return None

class Strategies:
    def __init__(self, stock_data):
        self.stock_data = stock_data
        self.current_price = self.stock_data['current_price']
        self.open_price = self.stock_data['open_price']

    def price(self, target_price):
        print(self.current_price)
        print(target_price - self.current_price)

    def percent(self, target_percent):
        percent_drop = ((self.open_price - self.current_price) / self.open_price) * 100
        print(target_percent - percent_drop)

class DiscordBot():
    def __init__(self, bot):
        self.bot = bot
        self.alert_commands()

    async def on_ready():
        print(f'Logged in as {bot.user} ')

    def alert_commands(self):
        @self.bot.command()
        async def setalert(ctx, ticker: str, threshold: str):
            threshold = float(threshold)
            await ctx.send(f"Alert set for {ticker} at {threshold}")
            user_id = ctx.author.id

discord_bot = DiscordBot(bot)

# Run the bot with your token
bot.run(TOKEN)