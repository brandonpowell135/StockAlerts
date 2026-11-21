import asyncio
import random


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
        await ctx.send("BoT hElP i DoNt KnOw HoW tO dO iT.....\n")
        await asyncio.sleep(2)
        await ctx.send("Dumbass look\n")
        await asyncio.sleep(2)
        await ctx.send(
            "**/setalertprice** set an alert for when a stock drops to a price\n"
            "**/setalertpercent** set an alert for a daily move - negative for a drop, positive for a gain\n"
            "**/setalertsma** alert when a stock crosses its 20/50/100/200-day moving average\n"
            "**/setalertrsi** alert when RSI crosses a level (below 30 = oversold, above 70 = overbought)\n"
            "**/myalerts** shows you all your alerts, numbered\n"
            "**/removealert** removes one alert by its number, **/removealerts** removes ALL of them\n"
            "**/quote** price, daily move, moving averages and RSI for a stock\n"
            "**/watchlist add/remove/show** the server watchlist, recapped every weekday at 4:10pm ET\n"
            "**/backtest** see how buying $100 on every X% daily drop would have done"
        )