import asyncio
import json
import logging
import os
from datetime import datetime, time
from zoneinfo import ZoneInfo

import discord
import yfinance as yf
from discord.ext import tasks

log = logging.getLogger(__name__)

# Where alerts are persisted. In Docker this lives on a volume (/app/data) so it
# survives image updates.
ALERTS_FILE = os.getenv("ALERTS_FILE", os.path.join("data", "alerts.json"))
CHECK_INTERVAL_MINUTES = float(os.getenv("CHECK_INTERVAL_MINUTES", "15"))
MAX_ALERTS_PER_USER = 25

MARKET_TZ = ZoneInfo("America/New_York")
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 5)  # a few minutes past close so the final print is caught

alerts = []


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def load_alerts_from_file(path=ALERTS_FILE):
    """Load alerts; a missing, empty or corrupt file yields an empty list."""
    try:
        with open(path, "r") as file:
            content = file.read()
    except FileNotFoundError:
        return []
    if not content.strip():
        return []
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        log.exception("Could not parse %s; starting with no alerts", path)
        return []
    return data if isinstance(data, list) else []


def save_alerts_to_file(path=ALERTS_FILE):
    """Atomically write alerts so a crash mid-write can't corrupt the file."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w") as file:
        json.dump(alerts, file, indent=2)
    os.replace(tmp_path, path)


# ---------------------------------------------------------------------------
# Market data and pure helpers
# ---------------------------------------------------------------------------
def normalize_ticker(ticker):
    return ticker.strip().upper()


def get_stock_data(ticker):
    """Blocking yfinance lookup. Call via asyncio.to_thread from async code."""
    try:
        data = yf.Ticker(ticker).history(period="5d")
    except Exception:
        log.exception("yfinance lookup failed for %s", ticker)
        return None
    if data is None or len(data) < 2:
        return None
    return {
        "ticker": ticker,
        "open_price": float(data["Open"].iloc[-1]),
        "current_price": float(data["Close"].iloc[-1]),
        "prev_close_price": float(data["Close"].iloc[-2]),
        "as_of": data.index[-1].date().isoformat(),
    }


def percent_calc(prev_close_price, current_price):
    return ((current_price - prev_close_price) / prev_close_price) * 100


def percent_alert_triggered(target_percent, change_percent):
    """Negative targets fire on drops at least that big, positive on gains."""
    if target_percent < 0:
        return change_percent <= target_percent
    return change_percent >= target_percent


def price_alert_triggered(target_price, current_price):
    return current_price <= target_price


def is_market_open(now=None):
    now = now or datetime.now(MARKET_TZ)
    now = now.astimezone(MARKET_TZ)
    return now.weekday() < 5 and MARKET_OPEN <= now.time() <= MARKET_CLOSE


def describe_alert(alert):
    if "target_price" in alert:
        return f"**{alert['ticker']}** at $**{alert['target_price']}**"
    return f"**{alert['ticker']}** at **{alert['target_percent']}**%"


# ---------------------------------------------------------------------------
# Discord wiring
# ---------------------------------------------------------------------------
def setup_stock_alerts(bot, CHANNEL_ID):
    """Register alert commands and start the alert loop.

    Must be called from within a running event loop (e.g. Bot.setup_hook).
    """
    global alerts
    alerts = load_alerts_from_file()
    log.info("Loaded %d alerts from %s", len(alerts), ALERTS_FILE)

    def user_alert_count(user_id):
        return sum(1 for alert in alerts if alert["user_id"] == user_id)

    async def validate_and_add(interaction, ticker, alert):
        if user_alert_count(interaction.user.id) >= MAX_ALERTS_PER_USER:
            await interaction.followup.send(
                f"You already have {MAX_ALERTS_PER_USER} alerts. Remove some with /removealerts first."
            )
            return False
        stock_data = await asyncio.to_thread(get_stock_data, ticker)
        if not stock_data:
            await interaction.followup.send(f"Invalid ticker: **{ticker}**.")
            return False
        alerts.append(alert)
        save_alerts_to_file()
        return True

    @bot.tree.command(name="setalertprice", description="Alert when a stock drops to a price")
    async def setalertprice(interaction: discord.Interaction, ticker: str, target_price: float):
        await interaction.response.defer()
        ticker = normalize_ticker(ticker)
        if target_price <= 0:
            await interaction.followup.send("Target price must be greater than 0.")
            return
        alert = {"user_id": interaction.user.id, "ticker": ticker, "target_price": target_price}
        if await validate_and_add(interaction, ticker, alert):
            await interaction.followup.send(f"Alert set for **{ticker}** at **{target_price}**")

    @bot.tree.command(
        name="setalertpercent",
        description="Alert on a daily move: negative for a drop, positive for a gain",
    )
    async def setalertpercent(interaction: discord.Interaction, ticker: str, target_percent: float):
        await interaction.response.defer()
        ticker = normalize_ticker(ticker)
        if target_percent == 0:
            await interaction.followup.send("Target percent can't be 0. Use e.g. -5 for a drop or 5 for a gain.")
            return
        alert = {"user_id": interaction.user.id, "ticker": ticker, "target_percent": target_percent}
        if await validate_and_add(interaction, ticker, alert):
            direction = "drop" if target_percent < 0 else "gain"
            await interaction.followup.send(
                f"Alert set for **{ticker}** at a **{abs(target_percent)}**% daily {direction}"
            )

    @bot.tree.command(name="myalerts", description="See all of your alerts")
    async def myalerts(interaction: discord.Interaction):
        user_alerts = [alert for alert in alerts if alert["user_id"] == interaction.user.id]
        if user_alerts:
            response = "\n".join(describe_alert(alert) for alert in user_alerts)
            await interaction.response.send_message(f"Your alerts:\n{response}")
        else:
            await interaction.response.send_message("You have no alerts set.")

    @bot.tree.command(name="removealerts", description="Remove all your alerts")
    async def removealerts(interaction: discord.Interaction):
        global alerts
        alerts = [alert for alert in alerts if alert["user_id"] != interaction.user.id]
        save_alerts_to_file()
        await interaction.response.send_message("All your alerts have been removed.")

    async def get_alert_channel():
        channel = bot.get_channel(CHANNEL_ID)
        if channel is None:
            try:
                channel = await bot.fetch_channel(CHANNEL_ID)
            except discord.DiscordException:
                log.exception("Alert channel %s is not reachable", CHANNEL_ID)
                return None
        return channel

    @tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
    async def check_alerts():
        # An unhandled exception would stop the loop permanently, so never let one escape.
        try:
            await run_alert_check()
        except Exception:
            log.exception("Alert check failed; will retry next interval")

    async def run_alert_check():
        if not alerts or not is_market_open():
            return
        channel = await get_alert_channel()
        if channel is None:
            return

        # One lookup per ticker per run, done off the event loop.
        tickers = sorted({alert["ticker"] for alert in alerts})
        results = await asyncio.gather(*(asyncio.to_thread(get_stock_data, t) for t in tickers))
        data_by_ticker = dict(zip(tickers, results))

        fired = []
        changed = False
        for alert in list(alerts):
            try:
                stock_data = data_by_ticker.get(alert["ticker"])
                if not stock_data:
                    continue
                current_price = stock_data["current_price"]
                mention = f"<@{alert['user_id']}>"

                target_price = alert.get("target_price")
                if target_price is not None and price_alert_triggered(target_price, current_price):
                    await channel.send(
                        f"{mention} Alert: **{alert['ticker']}** is at ${current_price:.2f}, "
                        f"hitting your target price of ${target_price}"
                    )
                    fired.append(alert)

                target_percent = alert.get("target_percent")
                if target_percent is not None and alert.get("last_triggered") != stock_data["as_of"]:
                    change = percent_calc(stock_data["prev_close_price"], current_price)
                    if percent_alert_triggered(target_percent, change):
                        await channel.send(
                            f"{mention} Alert: **{alert['ticker']}** hit your target of "
                            f"{target_percent}% with a daily move of {change:.2f}%"
                        )
                        # Percent alerts are recurring, but fire at most once per trading day.
                        alert["last_triggered"] = stock_data["as_of"]
                        changed = True
            except Exception:
                log.exception("Failed to process alert %s", alert)

        for alert in fired:
            if alert in alerts:
                alerts.remove(alert)
        if fired or changed:
            save_alerts_to_file()

    @check_alerts.before_loop
    async def before_check_alerts():
        await bot.wait_until_ready()

    check_alerts.start()
    return check_alerts
