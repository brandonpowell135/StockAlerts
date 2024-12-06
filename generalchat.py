import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv

def general_commands(bot):
    # Define a simple command
    @bot.command()
    async def pp(ctx):
        await ctx.send("poop")
