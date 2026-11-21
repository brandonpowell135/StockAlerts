import asyncio
import json
from datetime import datetime

import discord
import pytest
from discord.ext import commands

import market
from conftest import FakeChannel, FakeInteraction, make_history
from stockalerts import MARKET_TZ


def quote(ticker, price, prev, as_of="2026-11-20"):
    return {"ticker": ticker, "current_price": price, "prev_close_price": prev, "as_of": as_of}


def test_format_recap_sorts_by_move_and_handles_empty():
    rows = market.quote_rows([quote("SPY", 101, 100), quote("TSLA", 90, 100), None, quote("NVDA", 110, 100)])
    text = market.format_recap(rows, "Daily recap")
    lines = text.splitlines()
    assert lines[0] == "**Daily recap**"
    assert [line.split()[1] for line in lines[2:5]] == ["NVDA", "SPY", "TSLA"]
    assert "🔴 TSLA" in text and "-10.00%" in text
    assert "No data available" in market.format_recap([], "Daily recap")


def test_is_trading_day_close():
    assert market.is_trading_day_close([None, quote("SPY", 1, 1, "2026-11-20")], "2026-11-20")
    # Holiday: data still ends on the previous session.
    assert not market.is_trading_day_close([quote("SPY", 1, 1, "2026-11-25")], "2026-11-26")


def test_quote_summary_and_format():
    history = make_history([100.0 + i * 0.5 for i in range(250)])
    q = market.summarize_history("SPY", history)
    assert q["price"] == pytest.approx(224.5)
    assert q["sma50"] == pytest.approx(sum(100 + i * 0.5 for i in range(200, 250)) / 50)
    assert q["rsi"] == 100.0  # only ever went up
    text = market.format_quote(q)
    assert text.startswith("**SPY** $224.50 (+0.22% today, as of 2026-11-20)")
    assert "50-day SMA: $212.25 (price is above)" in text
    assert "RSI(14): 100.0 – overbought" in text

    short = market.summarize_history("NEW", make_history([10.0, 11.0, 12.0]))
    text = market.format_quote(short)
    assert "200-day SMA: not enough history" in text and "RSI" not in text


# ---------------------------------------------------------------------------
# Commands and recap, with a never-logged-in Bot
# ---------------------------------------------------------------------------
@pytest.fixture
def market_bot(tmp_path, monkeypatch):
    path = tmp_path / "watchlist.json"
    monkeypatch.setattr(market, "WATCHLIST_FILE", str(path))
    prices = {"SPY": (101.0, 100.0), "TSLA": (95.0, 100.0)}
    monkeypatch.setattr(
        market, "get_stock_data",
        lambda t: quote(t, *prices[t]) if t in prices else None,
    )
    channel = FakeChannel()

    async def build():
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        bot.get_channel = lambda channel_id: channel
        loop, post_recap = market.setup_market(bot, 123)
        loop.cancel()
        return bot, post_recap

    bot, post_recap = asyncio.run(build())
    return bot, post_recap, channel, path


def watchlist_cmd(bot, sub, **kwargs):
    interaction = FakeInteraction()
    group = bot.tree.get_command("watchlist")
    asyncio.run(group.get_command(sub).callback(interaction, **kwargs))
    return interaction.messages[-1]


def test_watchlist_add_remove_show(market_bot):
    bot, _, _, path = market_bot
    assert watchlist_cmd(bot, "add", ticker="spy") == "Added **SPY** to the watchlist."
    assert "already on" in watchlist_cmd(bot, "add", ticker="SPY")
    assert "Invalid ticker" in watchlist_cmd(bot, "add", ticker="NOPE")
    assert watchlist_cmd(bot, "add", ticker="tsla") == "Added **TSLA** to the watchlist."
    assert json.loads(path.read_text()) == ["SPY", "TSLA"]

    shown = watchlist_cmd(bot, "show")
    assert "SPY" in shown and "+1.00%" in shown and "-5.00%" in shown

    assert "Removed **TSLA**" in watchlist_cmd(bot, "remove", ticker="TSLA")
    assert "isn't on" in watchlist_cmd(bot, "remove", ticker="TSLA")
    assert json.loads(path.read_text()) == ["SPY"]


def test_watchlist_cap(market_bot, monkeypatch):
    bot, _, _, _ = market_bot
    monkeypatch.setattr(market, "watchlist", [f"T{i}" for i in range(market.MAX_WATCHLIST)])
    assert "full" in watchlist_cmd(bot, "add", ticker="SPY")


class FixedDatetime:
    value = None

    @classmethod
    def now(cls, tz=None):
        return cls.value


@pytest.mark.parametrize(
    "now, expect_post",
    [
        (datetime(2026, 11, 20, 16, 10, tzinfo=MARKET_TZ), True),   # Friday, data from today
        (datetime(2026, 11, 21, 16, 10, tzinfo=MARKET_TZ), False),  # Saturday
        (datetime(2026, 11, 26, 16, 10, tzinfo=MARKET_TZ), False),  # Thanksgiving: data is stale
    ],
)
def test_recap_posts_only_on_trading_days(market_bot, monkeypatch, now, expect_post):
    bot, post_recap, channel, _ = market_bot
    monkeypatch.setattr(market, "watchlist", ["SPY", "TSLA"])
    FixedDatetime.value = now
    monkeypatch.setattr(market, "datetime", FixedDatetime)
    asyncio.run(post_recap())
    assert bool(channel.messages) is expect_post
    if expect_post:
        assert channel.messages[0].startswith("**Daily recap – Fri Nov 20**")
