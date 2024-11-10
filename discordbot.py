import discord
import os
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Get the token from the environment variable
TOKEN = os.getenv('DISCORD_TOKEN')
print(f'Token loaded: {TOKEN}')

# Create a bot instance with a command prefix
intents = discord.Intents.default()
intents.message_content = True  # Make sure to allow reading messages
bot = commands.Bot(command_prefix="!", intents=intents)

# Define a simple command
@bot.command()
async def hello(ctx):
    await ctx.send("Hello, I am your bot!")

# Start the bot
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

# Run the bot with your token
bot.run(TOKEN)