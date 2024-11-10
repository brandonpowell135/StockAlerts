import yfinance as yf
import pandas as pd
import discord
from discord.ext import commands, tasks
import os 
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Set up the bot with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix= "!", intents=intents)

# Set parameters
ticker = "UPRO"
investment_per_entry = 100
threshold = -0.05  # 10% drop
start_date = "2020-01-01"  # Starting date for data, adjust as needed

# Fetch historical data
data = yf.download(ticker, start=start_date)

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

# Ensure total_shares is a single number by converting to a float explicitly
total_shares = float(total_shares.iloc[0]) if isinstance(total_shares, pd.Series) else float(total_shares)

# Calculate average cost safely
average_cost = total_invested / total_shares if total_shares > 0 else 0

# Calculate P/L
# To do



@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} ')

# Define a simple command
@bot.command()
async def status(ctx):
    await ctx.send(f"Buying {ticker} everytime there is a drop of 10% or more results:")
    await ctx.send(f"Number of Entries: {len(drop_days)}")
    await ctx.send(f"Total Invested: ${total_invested:.2f}")
    await ctx.send(f"Total Shares Purchased: {total_shares:.4f}")
    await ctx.send(f"Average Cost per Share: ${average_cost:.2f}")

# Run the bot with your tocken
bot.run(TOKEN)
