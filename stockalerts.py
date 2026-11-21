import asyncio
import json
import logging
import os
from datetime import datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

import discord
import yfinance as yf
from discord import app_commands
from discord.ext import tasks

import indicators

log = logging.getLogger(__name__)

# Where alerts are persisted. In Docker this lives on a volume (/app/data) so it
# survives image updates.
ALERTS_FILE = os.getenv("ALERTS_FILE", os.path.join("data", "alerts.json"))
CHECK_INTERVAL_MINUTES = float(os.getenv("CHECK_INTERVAL_MINUTES", "15"))
MAX_ALERTS_PER_USER = 25

MARKET_TZ = ZoneInfo("America/New_York")
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 5)  # a few minutes past close so the final print is caught

SMA_WINDOWS = [20, 50, 100, 200]
DEFAULT_RSI_THRESHOLDS = {"below": 30.0, "above": 70.0}
DIRECTION_CHOICES = [
    app_commands.Choice(name="above", value="above"),
    app_commands.Choice(name="below", value="below"),
]

alerts = []


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def load_json(path, default):
    """Load JSON; a missing, empty, corrupt or wrong-shaped file yields `default`."""
    try:
        with open(path, "r") as file:
            content = file.read()
    except FileNotFoundError:
        return default
    if not content.strip():
        return default
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        log.exception("Could not parse %s; starting empty", path)
        return default
    return data if isinstance(data, type(default)) else default


def save_json(path, data):
    """Atomically write JSON so a crash mid-write can't corrupt the file."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w") as file:
        json.dump(data, file, indent=2)
    os.replace(tmp_path, path)


def load_alerts_from_file(path=None):
    return load_json(path or ALERTS_FILE, [])


def save_alerts_to_file(path=None):
    save_json(path or ALERTS_FILE, alerts)


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
        "day_low": float(data["Low"].iloc[-1]),
        "day_high": float(data["High"].iloc[-1]),
        "as_of": data.index[-1].date().isoformat(),
    }


def get_daily_history(ticker, period="1y"):
    """Blocking: a year of daily bars (today's row is live during market hours), or None."""
    try:
        data = yf.Ticker(ticker).history(period=period)
    except Exception:
        log.exception("yfinance history failed for %s", ticker)
        return None
    if data is None or len(data) < 2:
        return None
    return data


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


def alert_type(alert):
    """Older saved alerts have no "type"; infer it from their keys."""
    if "type" in alert:
        return alert["type"]
    return "price" if "target_price" in alert else "percent"


def needs_history(alert):
    return alert_type(alert) in ("sma", "rsi")


def describe_alert(alert):
    kind = alert_type(alert)
    ticker = alert["ticker"]
    if kind == "price":
        return f"**{ticker}** at $**{alert['target_price']}**"
    if kind == "percent":
        return f"**{ticker}** at **{alert['target_percent']}**%"
    if kind == "sma":
        return f"**{ticker}** crosses {alert['direction']} its **{alert['window']}-day SMA**"
    if kind == "rsi":
        return f"**{ticker}** RSI crosses {alert['direction']} **{alert['threshold']:g}**"
    return f"**{ticker}** ({kind})"


def recurring_already_fired(alert, as_of):
    return alert.get("last_triggered") == as_of


def evaluate_alert(alert, stock_data, history=None):
    """Return the alert message (without the @mention) if it should fire now, else None.

    Price alerts are one-shot; the caller removes them. The others are recurring and
    the caller records `last_triggered` so they fire at most once per trading day.
    """
    kind = alert_type(alert)
    ticker = alert["ticker"]

    if kind == "price":
        if stock_data is None:
            return None
        current = stock_data["current_price"]
        if price_alert_triggered(alert["target_price"], current):
            return f"**{ticker}** is at ${current:.2f}, hitting your target price of ${alert['target_price']}"
        return None

    if kind == "percent":
        if stock_data is None or recurring_already_fired(alert, stock_data["as_of"]):
            return None
        change = percent_calc(stock_data["prev_close_price"], stock_data["current_price"])
        if percent_alert_triggered(alert["target_percent"], change):
            return f"**{ticker}** hit your target of {alert['target_percent']}% with a daily move of {change:.2f}%"
        return None

    if history is None or recurring_already_fired(alert, history_as_of(history)):
        return None
    closes = history["Close"]
    price = float(closes.iloc[-1])

    if kind == "sma":
        did_cross, average = indicators.sma_cross(closes, alert["window"], alert["direction"])
        if did_cross:
            return (f"**{ticker}** crossed {alert['direction']} its {alert['window']}-day SMA "
                    f"(${price:.2f} vs SMA ${average:.2f})")
        return None

    if kind == "rsi":
        did_cross, value = indicators.rsi_cross(closes, alert["threshold"], alert["direction"])
        if did_cross:
            return (f"**{ticker}** RSI crossed {alert['direction']} {alert['threshold']:g} "
                    f"(RSI {value:.1f}, price ${price:.2f})")
        return None

    log.warning("Unknown alert type %r", kind)
    return None


def history_as_of(history):
    return history.index[-1].date().isoformat()


def alert_as_of(alert, stock_data, history):
    if needs_history(alert):
        return history_as_of(history)
    return stock_data["as_of"]


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

    def user_alerts(user_id):
        return [alert for alert in alerts if alert["user_id"] == user_id]

    async def validate_and_add(interaction, ticker, alert):
        if len(user_alerts(interaction.user.id)) >= MAX_ALERTS_PER_USER:
            await interaction.followup.send(
                f"You already have {MAX_ALERTS_PER_USER} alerts. Remove some with /removealert first."
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

    @bot.tree.command(name="setalertsma", description="Alert when a stock crosses a moving average")
    @app_commands.describe(window="Moving average length in days", direction="Cross above or below it")
    @app_commands.choices(
        window=[app_commands.Choice(name=f"{w}-day", value=w) for w in SMA_WINDOWS],
        direction=DIRECTION_CHOICES,
    )
    async def setalertsma(
        interaction: discord.Interaction,
        ticker: str,
        window: app_commands.Choice[int],
        direction: app_commands.Choice[str],
    ):
        await interaction.response.defer()
        ticker = normalize_ticker(ticker)
        alert = {"user_id": interaction.user.id, "ticker": ticker, "type": "sma",
                 "window": window.value, "direction": direction.value}
        if await validate_and_add(interaction, ticker, alert):
            await interaction.followup.send(f"Alert set: {describe_alert(alert)}")

    @bot.tree.command(name="setalertrsi", description="Alert when a stock's RSI(14) crosses a level")
    @app_commands.describe(
        direction="below = oversold signal, above = overbought signal",
        threshold="RSI level (default 30 for below, 70 for above)",
    )
    @app_commands.choices(direction=DIRECTION_CHOICES)
    async def setalertrsi(
        interaction: discord.Interaction,
        ticker: str,
        direction: app_commands.Choice[str],
        threshold: Optional[app_commands.Range[float, 1, 99]] = None,
    ):
        await interaction.response.defer()
        ticker = normalize_ticker(ticker)
        level = threshold if threshold is not None else DEFAULT_RSI_THRESHOLDS[direction.value]
        alert = {"user_id": interaction.user.id, "ticker": ticker, "type": "rsi",
                 "threshold": float(level), "direction": direction.value}
        if await validate_and_add(interaction, ticker, alert):
            await interaction.followup.send(f"Alert set: {describe_alert(alert)}")

    @bot.tree.command(name="myalerts", description="See all of your alerts")
    async def myalerts(interaction: discord.Interaction):
        mine = user_alerts(interaction.user.id)
        if mine:
            response = "\n".join(f"{i}. {describe_alert(alert)}" for i, alert in enumerate(mine, start=1))
            await interaction.response.send_message(
                f"Your alerts:\n{response}\n\nRemove one with `/removealert <number>`."
            )
        else:
            await interaction.response.send_message("You have no alerts set.")

    @bot.tree.command(name="removealert", description="Remove one alert by its number in /myalerts")
    async def removealert(interaction: discord.Interaction, number: app_commands.Range[int, 1]):
        mine = user_alerts(interaction.user.id)
        if number > len(mine):
            await interaction.response.send_message(
                f"You don't have an alert #{number}. Check `/myalerts` for the numbers."
            )
            return
        alert = mine[number - 1]
        alerts.remove(alert)
        save_alerts_to_file()
        await interaction.response.send_message(f"Removed alert: {describe_alert(alert)}")

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

    async def fetch_all(func, tickers):
        results = await asyncio.gather(*(asyncio.to_thread(func, t) for t in tickers))
        return dict(zip(tickers, results))

    async def run_alert_check():
        if not alerts or not is_market_open():
            return
        channel = await get_alert_channel()
        if channel is None:
            return

        # One lookup per ticker per run, done off the event loop. Daily history is only
        # fetched for tickers that have SMA/RSI alerts.
        quote_tickers = sorted({a["ticker"] for a in alerts if not needs_history(a)})
        history_tickers = sorted({a["ticker"] for a in alerts if needs_history(a)})
        quotes = await fetch_all(get_stock_data, quote_tickers)
        histories = await fetch_all(get_daily_history, history_tickers)

        fired = []
        changed = False
        for alert in list(alerts):
            try:
                stock_data = quotes.get(alert["ticker"])
                history = histories.get(alert["ticker"])
                message = evaluate_alert(alert, stock_data, history)
                if message is None:
                    continue
                await channel.send(f"<@{alert['user_id']}> Alert: {message}")
                if alert_type(alert) == "price":
                    fired.append(alert)
                else:
                    alert["last_triggered"] = alert_as_of(alert, stock_data, history)
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
