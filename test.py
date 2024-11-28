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

class Discordbot:
    def __init__(self,bot):
        self.bot = bot
        self.bot.command()(self.ss)
        
    @bot.event
    async def on_ready():
        print(f'Logged in as {bot.user} ')

    @bot.command()
    async def setalert(ctx, ticker: str, threshold: float):
    #async def ss(ctx):
        response = f"alert for [ {ticker} ] is set at [ {threshold} ]%"
        await ctx.send(response)
        print(ticker,threshold)
        return threshold

#strategies = Strategies(get_stock_data(threshold))
#target_price = 150
#target_percent = threshold
#strategies.price(target_price)
#strategies.percent(target_percent)

# Run the bot with your token
bot.run(TOKEN)
#test
