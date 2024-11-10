import discord
from discord.ext import commands, tasks
import yfinance as yf
import os 
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Set up the bot with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix= "!", intents=intents)

# Stock variables
ticker = "TQQQ"
channel_ID = 1304872669740667000

# Function to get the latest stock price
def get_stock_price(ticker):
    stock = yf.Ticker(ticker)
    data = stock.history(period="1d")
    if not data.empty:
        open_price = data['Open'][0]
        close_price = data['Close'][0]
        
        # Calculate percent drop
        percent_drop = ((open_price - close_price) /open_price) * 100
        return percent_drop
    return None # Return none if no dt is available

# Send message id stock drops by 10%
@tasks.loop(minutes=5) # Run the check every 5 minutes
async def monitor_stock():
    percent_drop = get_stock_price(ticker)
    
    if percent_drop is not None and percent_drop >= 10:
        # Send a message to discord
        channel = bot.get_channel(channel_ID)
        await channel.send(f"Alert: {ticker} stock has dropped by {percent_drop:.2f}%!")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} ')
    monitor_stock.start() # Start monitoring stock when the bot is ready

# Define a simple command
@bot.command()
async def pp(ctx):
    await ctx.send("poop")

# Run the bot with your tocken
bot.run(TOKEN)
