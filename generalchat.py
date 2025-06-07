import discord
from discord.ext import commands, tasks
import random
import asyncio


def general_commands(bot):
    # List of random messages
    random_messages = [
        "Hello there!",
        "How's it going?",
        "Did you know you’re awesome?",
        "Random fact: Penguins mate for life!",
        "Here’s a random message for you!"
    ]

    @bot.command()
    async def pp(ctx):
        # Pick a random message
        message = random.choice(random_messages)
        await ctx.send(message)

    @bot.command()
    async def bothelp(ctx):
        # Pick a random message
        await ctx.send("BoT hElP i DoNt KnOw HoW tO dO iT.....\n")
        # Delay (e.g., 5 seconds)
        await asyncio.sleep(2)
        await ctx.send("Dumbass look\n")
        await asyncio.sleep(2)
        await ctx.send("**/setalertprice** you set an alert for the price you want. \n")
        await asyncio.sleep(2)
        await ctx.send("**/setalertpercent** you set an alert for the percent change you want - put negative for a drop positive for a gain\n")
        await asyncio.sleep(2)
        await ctx.send("**/myalerts** shows you all your alerts set\n")        
        await asyncio.sleep(2)
        await ctx.send("**/removealerts** remove ALL your alerts\n\n")