import asyncio
from datetime import date

import discord
import yfinance as yf

from stockalerts import normalize_ticker, percent_calc

INVESTMENT_PER_ENTRY = 100  # dollars bought on each qualifying drop


def run_drop_backtest(history, drop_percent, investment_per_entry=INVESTMENT_PER_ENTRY):
    """Buy `investment_per_entry` at the close of every day that fell `drop_percent`% or more.

    Returns None if no day qualified. Compares against investing the same total
    amount as a lump sum at the first close of the period (buy-and-hold).
    """
    threshold = -abs(drop_percent)
    closes = history["Close"]
    daily_change = closes.pct_change() * 100
    drop_closes = closes[daily_change <= threshold]
    if drop_closes.empty:
        return None

    entries = len(drop_closes)
    total_invested = entries * investment_per_entry
    total_shares = float((investment_per_entry / drop_closes).sum())
    current_price = float(closes.iloc[-1])
    value = total_shares * current_price

    hold_shares = total_invested / float(closes.iloc[0])
    hold_value = hold_shares * current_price

    return {
        "threshold": threshold,
        "entries": entries,
        "total_invested": total_invested,
        "total_shares": total_shares,
        "average_cost": total_invested / total_shares,
        "current_price": current_price,
        "value": value,
        "percent_gain": percent_calc(total_invested, value),
        "hold_value": hold_value,
        "hold_percent_gain": percent_calc(total_invested, hold_value),
    }


def backtest(bot):
    @bot.tree.command(name="backtest", description="Backtest buying $100 every time a stock drops X% in a day")
    async def backtest_command(
        interaction: discord.Interaction, ticker: str, drop_percent: float, start_date: str
    ):
        await interaction.response.defer()
        ticker = normalize_ticker(ticker)

        try:
            start = date.fromisoformat(start_date)
        except ValueError:
            await interaction.followup.send("Start date must be in YYYY-MM-DD format, e.g. 2020-01-01.")
            return
        if start >= date.today():
            await interaction.followup.send("Start date must be in the past.")
            return
        if drop_percent == 0:
            await interaction.followup.send("Drop percent can't be 0. Use e.g. 3 for days that fell 3% or more.")
            return

        try:
            history = await asyncio.to_thread(lambda: yf.Ticker(ticker).history(start=start.isoformat()))
        except Exception:
            history = None
        if history is None or len(history) < 2:
            await interaction.followup.send(f"No data found for **{ticker}** starting from {start}.")
            return

        result = run_drop_backtest(history, drop_percent)
        if result is None:
            await interaction.followup.send(
                f"No daily drops of {abs(drop_percent)}% or more found for **{ticker}** since {start}."
            )
            return

        await interaction.followup.send(
            f"Backtesting **{ticker}**: buy ${INVESTMENT_PER_ENTRY} on every daily drop of "
            f"{abs(result['threshold'])}% or more since {start}\n"
            f"- Number of Entries: {result['entries']}\n"
            f"- Total Invested: ${result['total_invested']:,.2f}\n"
            f"- Total Shares Purchased: {result['total_shares']:.4f}\n"
            f"- Average Cost per Share: ${result['average_cost']:,.2f}\n"
            f"- Current Price: ${result['current_price']:,.2f}\n"
            f"- Current Value: ${result['value']:,.2f} ({result['percent_gain']:+.2f}%)\n"
            f"- Buy-and-hold (same amount at the start): ${result['hold_value']:,.2f} "
            f"({result['hold_percent_gain']:+.2f}%)"
        )
