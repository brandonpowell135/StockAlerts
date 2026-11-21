import asyncio
import json
from datetime import datetime

import discord
import pytest
from discord.ext import commands

import stockalerts
from conftest import FakeChannel, FakeInteraction, choice, make_history
from stockalerts import (
    MARKET_TZ,
    is_market_open,
    load_alerts_from_file,
    percent_alert_triggered,
    percent_calc,
    price_alert_triggered,
)


def test_percent_calc():
    assert percent_calc(100, 95) == pytest.approx(-5)
    assert percent_calc(100, 110) == pytest.approx(10)


@pytest.mark.parametrize(
    "target, change, expected",
    [
        (-5, -6, True),   # drop alert, bigger drop
        (-5, -5, True),
        (-5, -2, False),  # drop alert, smaller drop
        (-5, 3, False),   # drop alert, stock went up
        (5, 6, True),     # gain alert, bigger gain
        (5, 2, False),    # gain alert, smaller gain (old code fired here)
        (5, -3, False),   # gain alert, stock went down (old code fired here)
    ],
)
def test_percent_alert_triggered(target, change, expected):
    assert percent_alert_triggered(target, change) is expected


def test_price_alert_triggered():
    assert price_alert_triggered(100, 99.5)
    assert not price_alert_triggered(100, 100.5)


def test_market_hours():
    assert is_market_open(datetime(2026, 11, 20, 10, 0, tzinfo=MARKET_TZ))      # Friday morning
    assert not is_market_open(datetime(2026, 11, 20, 8, 0, tzinfo=MARKET_TZ))   # before open
    assert not is_market_open(datetime(2026, 11, 20, 17, 0, tzinfo=MARKET_TZ))  # after close
    assert not is_market_open(datetime(2026, 11, 21, 12, 0, tzinfo=MARKET_TZ))  # Saturday


@pytest.mark.parametrize("content", [None, "", "   \n", "{not json", '{"a": 1}'])
def test_load_alerts_tolerates_missing_empty_or_bad_files(tmp_path, content):
    path = tmp_path / "alerts.json"
    if content is not None:
        path.write_text(content)
    assert load_alerts_from_file(str(path)) == []


def test_save_then_load_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "nested" / "alerts.json"
    monkeypatch.setattr(stockalerts, "alerts", [{"user_id": 1, "ticker": "SPY", "target_price": 400.0}])
    stockalerts.save_alerts_to_file(str(path))
    assert load_alerts_from_file(str(path)) == [{"user_id": 1, "ticker": "SPY", "target_price": 400.0}]


# ---------------------------------------------------------------------------
# Alert loop, driven with a real (never logged-in) Bot and fake channel/data
# ---------------------------------------------------------------------------
def run_check(tmp_path, monkeypatch, initial_alerts, prices, runs=1, fail_tickers=(), histories=None):
    """Run the alert check `runs` times; returns (channel, alerts_on_disk)."""
    path = tmp_path / "alerts.json"
    path.write_text(json.dumps(initial_alerts))
    monkeypatch.setattr(stockalerts, "ALERTS_FILE", str(path))
    monkeypatch.setattr(stockalerts.save_alerts_to_file, "__defaults__", (str(path),))
    monkeypatch.setattr(stockalerts.load_alerts_from_file, "__defaults__", (str(path),))
    monkeypatch.setattr(stockalerts, "is_market_open", lambda now=None: True)

    def fake_get_stock_data(ticker):
        if ticker in fail_tickers:
            raise RuntimeError("network down")
        current, prev = prices[ticker]
        return {"ticker": ticker, "open_price": prev, "current_price": current,
                "prev_close_price": prev, "as_of": "2026-11-20"}

    monkeypatch.setattr(stockalerts, "get_stock_data", fake_get_stock_data)
    monkeypatch.setattr(stockalerts, "get_daily_history", lambda ticker: (histories or {}).get(ticker))
    channel = FakeChannel()

    async def scenario():
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        bot.get_channel = lambda channel_id: channel
        loop = stockalerts.setup_stock_alerts(bot, 123)
        loop.cancel()  # we drive it by hand instead of on a timer
        for _ in range(runs):
            await loop()

    asyncio.run(scenario())
    return channel, json.loads(path.read_text())


def test_price_alert_fires_once_and_is_removed_from_disk(tmp_path, monkeypatch):
    channel, saved = run_check(
        tmp_path, monkeypatch,
        [{"user_id": 1, "ticker": "SPY", "target_price": 400.0},
         {"user_id": 2, "ticker": "SPY", "target_price": 300.0}],
        prices={"SPY": (399.0, 410.0)},
        runs=2,
    )
    assert len(channel.messages) == 1
    assert "<@1>" in channel.messages[0]
    assert saved == [{"user_id": 2, "ticker": "SPY", "target_price": 300.0}]


def test_percent_alert_fires_once_per_day_and_is_kept(tmp_path, monkeypatch):
    channel, saved = run_check(
        tmp_path, monkeypatch,
        [{"user_id": 1, "ticker": "TSLA", "target_percent": -5.0}],
        prices={"TSLA": (90.0, 100.0)},  # -10%
        runs=3,
    )
    assert len(channel.messages) == 1
    assert saved == [{"user_id": 1, "ticker": "TSLA", "target_percent": -5.0, "last_triggered": "2026-11-20"}]


def test_gain_alert_does_not_fire_on_small_move(tmp_path, monkeypatch):
    channel, _ = run_check(
        tmp_path, monkeypatch,
        [{"user_id": 1, "ticker": "AAPL", "target_percent": 5.0}],
        prices={"AAPL": (101.0, 100.0)},  # +1%
    )
    assert channel.messages == []


def test_loop_survives_data_errors(tmp_path, monkeypatch):
    # A failing lookup must not stop the loop (previously it killed alerts until restart).
    channel, saved = run_check(
        tmp_path, monkeypatch,
        [{"user_id": 1, "ticker": "BAD", "target_price": 10.0}],
        prices={},
        runs=2,
        fail_tickers={"BAD"},
    )
    assert channel.messages == []
    assert len(saved) == 1


# ---------------------------------------------------------------------------
# Alert types, evaluation, and the new commands
# ---------------------------------------------------------------------------
def test_old_saved_alerts_infer_their_type():
    assert stockalerts.alert_type({"user_id": 1, "ticker": "SPY", "target_price": 1.0}) == "price"
    assert stockalerts.alert_type({"user_id": 1, "ticker": "SPY", "target_percent": -5.0}) == "percent"
    assert stockalerts.alert_type({"type": "rsi"}) == "rsi"


SMA_ALERT = {"user_id": 1, "ticker": "AAPL", "type": "sma", "window": 20, "direction": "above"}
RSI_ALERT = {"user_id": 1, "ticker": "AAPL", "type": "rsi", "threshold": 30.0, "direction": "below"}
CROSSES_SMA = make_history([100.0] * 20 + [99.0, 105.0])
CRASHES = make_history([100.0 + i for i in range(20)] + [90.0, 80.0, 70.0])


def test_evaluate_sma_and_rsi_alerts():
    assert "crossed above its 20-day SMA" in stockalerts.evaluate_alert(SMA_ALERT, None, CROSSES_SMA)
    assert stockalerts.evaluate_alert(SMA_ALERT, None, make_history([100.0] * 22)) is None
    assert stockalerts.evaluate_alert(SMA_ALERT, None, None) is None  # data unavailable
    # Already fired for this trading day.
    fired_today = {**SMA_ALERT, "last_triggered": "2026-11-20"}
    assert stockalerts.evaluate_alert(fired_today, None, CROSSES_SMA) is None

    # RSI crosses below 30 on exactly one bar of the crash; find it and check the message.
    messages = [stockalerts.evaluate_alert(RSI_ALERT, None, CRASHES.iloc[:end]) for end in range(16, 24)]
    assert sum(m is not None for m in messages) == 1
    assert "RSI crossed below 30" in next(m for m in messages if m)


def test_sma_alert_fires_once_per_day_in_loop(tmp_path, monkeypatch):
    channel, saved = run_check(
        tmp_path, monkeypatch, [SMA_ALERT], prices={}, runs=3, histories={"AAPL": CROSSES_SMA},
    )
    assert len(channel.messages) == 1
    assert channel.messages[0].startswith("<@1> Alert: **AAPL** crossed above")
    assert saved == [{**SMA_ALERT, "last_triggered": "2026-11-20"}]


def test_describe_new_alert_types():
    assert stockalerts.describe_alert(SMA_ALERT) == "**AAPL** crosses above its **20-day SMA**"
    assert stockalerts.describe_alert(RSI_ALERT) == "**AAPL** RSI crosses below **30**"


def setup_commands(tmp_path, monkeypatch, initial_alerts):
    path = tmp_path / "alerts.json"
    path.write_text(json.dumps(initial_alerts))
    monkeypatch.setattr(stockalerts, "ALERTS_FILE", str(path))
    monkeypatch.setattr(stockalerts, "get_stock_data", lambda t: {"as_of": "2026-11-20"})

    async def build():
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        stockalerts.setup_stock_alerts(bot, 123).cancel()
        return bot

    return asyncio.run(build()), path


def call(bot, name, interaction, **kwargs):
    asyncio.run(bot.tree.get_command(name).callback(interaction, **kwargs))
    return interaction.messages[-1]


def test_myalerts_numbered_and_removealert_by_number(tmp_path, monkeypatch):
    bot, path = setup_commands(tmp_path, monkeypatch, [
        {"user_id": 1, "ticker": "SPY", "target_price": 400.0},
        {"user_id": 2, "ticker": "QQQ", "target_price": 300.0},  # someone else's
        {"user_id": 1, "ticker": "TSLA", "target_percent": -5.0},
        RSI_ALERT,
    ])
    listing = call(bot, "myalerts", FakeInteraction(1))
    assert "1. **SPY**" in listing and "2. **TSLA**" in listing and "3. **AAPL** RSI" in listing
    assert "QQQ" not in listing

    assert "Removed alert: **TSLA**" in call(bot, "removealert", FakeInteraction(1), number=2)
    assert "don't have an alert #5" in call(bot, "removealert", FakeInteraction(1), number=5)
    saved = json.loads(path.read_text())
    assert [a["ticker"] for a in saved] == ["SPY", "QQQ", "AAPL"]


def test_set_sma_and_rsi_alerts(tmp_path, monkeypatch):
    bot, path = setup_commands(tmp_path, monkeypatch, [])
    reply = call(bot, "setalertsma", FakeInteraction(7), ticker=" nvda ", window=choice(50), direction=choice("below"))
    assert reply == "Alert set: **NVDA** crosses below its **50-day SMA**"
    reply = call(bot, "setalertrsi", FakeInteraction(7), ticker="nvda", direction=choice("above"))
    assert reply == "Alert set: **NVDA** RSI crosses above **70**"  # default threshold
    saved = json.loads(path.read_text())
    assert saved == [
        {"user_id": 7, "ticker": "NVDA", "type": "sma", "window": 50, "direction": "below"},
        {"user_id": 7, "ticker": "NVDA", "type": "rsi", "threshold": 70.0, "direction": "above"},
    ]
