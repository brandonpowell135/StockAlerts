"""Market info commands: /quote, the shared /watchlist, and the daily close recap."""
import asyncio
import logging
import os
from datetime import datetime, time

import discord
from discord import app_commands
from discord.ext import tasks

import indicators
from stockalerts import (
    MARKET_TZ,
    get_daily_history,
    get_stock_data,
    load_json,
    normalize_ticker,
    percent_calc,
    save_json,
)

log = logging.getLogger(__name__)

WATCHLIST_FILE = os.getenv("WATCHLIST_FILE", os.path.join("data", "watchlist.json"))
MAX_WATCHLIST = 25
RECAP_TIME = time(16, 10, tzinfo=MARKET_TZ)

watchlist = []


# ---------------------------------------------------------------------------
# Pure formatting helpers
# ---------------------------------------------------------------------------
def summarize_history(ticker, history):
    """Quote numbers from daily history (today's row is live during market hours)."""
    closes = history["Close"]
    price = float(closes.iloc[-1])
    prev_close = float(closes.iloc[-2])
    sma50 = indicators.sma(closes, 50).iloc[-1]
    sma200 = indicators.sma(closes, 200).iloc[-1]
    rsi = indicators.rsi(closes).iloc[-1]
    return {
        "ticker": ticker,
        "price": price,
        "change": percent_calc(prev_close, price),
        "day_low": float(history["Low"].iloc[-1]),
        "day_high": float(history["High"].iloc[-1]),
        "sma50": None if sma50 != sma50 else float(sma50),  # NaN check
        "sma200": None if sma200 != sma200 else float(sma200),
        "rsi": None if rsi != rsi else float(rsi),
        "as_of": history.index[-1].date().isoformat(),
    }


def format_quote(q):
    lines = [
        f"**{q['ticker']}** ${q['price']:,.2f} ({q['change']:+.2f}% today, as of {q['as_of']})",
        f"Day range: ${q['day_low']:,.2f} – ${q['day_high']:,.2f}",
    ]
    for label, key in [("50-day SMA", "sma50"), ("200-day SMA", "sma200")]:
        value = q[key]
        if value is None:
            lines.append(f"{label}: not enough history")
        else:
            side = "above" if q["price"] > value else "below"
            lines.append(f"{label}: ${value:,.2f} (price is {side})")
    if q["rsi"] is not None:
        tag = " – oversold" if q["rsi"] < 30 else " – overbought" if q["rsi"] > 70 else ""
        lines.append(f"RSI(14): {q['rsi']:.1f}{tag}")
    return "\n".join(lines)


def format_recap(rows, title):
    """rows: list of (ticker, price, change_percent). Sorted biggest gain to biggest loss."""
    if not rows:
        return f"**{title}**\nNo data available."
    rows = sorted(rows, key=lambda r: r[2], reverse=True)
    width = max(len(r[0]) for r in rows)
    body = "\n".join(
        f"{'🟢' if change >= 0 else '🔴'} {ticker:<{width}}  {price:>10,.2f}  {change:+6.2f}%"
        for ticker, price, change in rows
    )
    return f"**{title}**\n```\n{body}\n```"


def is_trading_day_close(quotes, today):
    """True if at least one ticker has a bar for `today` (false on weekends and holidays)."""
    return any(q and q["as_of"] == today for q in quotes)


def quote_rows(quotes):
    return [
        (q["ticker"], q["current_price"], percent_calc(q["prev_close_price"], q["current_price"]))
        for q in quotes
        if q
    ]


# ---------------------------------------------------------------------------
# Discord wiring
# ---------------------------------------------------------------------------
async def fetch_quotes(tickers):
    return await asyncio.gather(*(asyncio.to_thread(get_stock_data, t) for t in tickers))


def setup_market(bot, channel_id):
    """Register /quote and /watchlist and start the daily recap. Call from setup_hook."""
    global watchlist
    watchlist = load_json(WATCHLIST_FILE, [])

    @bot.tree.command(name="quote", description="Price, daily move, moving averages and RSI for a stock")
    async def quote(interaction: discord.Interaction, ticker: str):
        await interaction.response.defer()
        ticker = normalize_ticker(ticker)
        history = await asyncio.to_thread(get_daily_history, ticker)
        if history is None:
            await interaction.followup.send(f"Invalid ticker: **{ticker}**.")
            return
        await interaction.followup.send(format_quote(summarize_history(ticker, history)))

    group = app_commands.Group(name="watchlist", description="The server's shared watchlist")

    @group.command(name="add", description="Add a ticker to the watchlist")
    async def watchlist_add(interaction: discord.Interaction, ticker: str):
        await interaction.response.defer()
        ticker = normalize_ticker(ticker)
        if ticker in watchlist:
            await interaction.followup.send(f"**{ticker}** is already on the watchlist.")
            return
        if len(watchlist) >= MAX_WATCHLIST:
            await interaction.followup.send(f"The watchlist is full ({MAX_WATCHLIST} tickers). Remove one first.")
            return
        if not await asyncio.to_thread(get_stock_data, ticker):
            await interaction.followup.send(f"Invalid ticker: **{ticker}**.")
            return
        watchlist.append(ticker)
        save_json(WATCHLIST_FILE, watchlist)
        await interaction.followup.send(f"Added **{ticker}** to the watchlist.")

    @group.command(name="remove", description="Remove a ticker from the watchlist")
    async def watchlist_remove(interaction: discord.Interaction, ticker: str):
        ticker = normalize_ticker(ticker)
        if ticker not in watchlist:
            await interaction.response.send_message(f"**{ticker}** isn't on the watchlist.")
            return
        watchlist.remove(ticker)
        save_json(WATCHLIST_FILE, watchlist)
        await interaction.response.send_message(f"Removed **{ticker}** from the watchlist.")

    @group.command(name="show", description="Show the watchlist with today's moves")
    async def watchlist_show(interaction: discord.Interaction):
        if not watchlist:
            await interaction.response.send_message("The watchlist is empty. Add tickers with `/watchlist add`.")
            return
        await interaction.response.defer()
        quotes = await fetch_quotes(list(watchlist))
        await interaction.followup.send(format_recap(quote_rows(quotes), "Watchlist"))

    bot.tree.add_command(group)

    @tasks.loop(time=RECAP_TIME)
    async def daily_recap():
        try:
            await post_recap()
        except Exception:
            log.exception("Daily recap failed")

    async def post_recap():
        now = datetime.now(MARKET_TZ)
        if now.weekday() >= 5 or not watchlist:
            return
        quotes = await fetch_quotes(list(watchlist))
        if not is_trading_day_close(quotes, now.date().isoformat()):
            log.info("No trading today (holiday?); skipping recap")
            return
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        await channel.send(format_recap(quote_rows(quotes), f"Daily recap – {now:%a %b %d}"))

    @daily_recap.before_loop
    async def before_daily_recap():
        await bot.wait_until_ready()

    daily_recap.start()
    return daily_recap, post_recap
