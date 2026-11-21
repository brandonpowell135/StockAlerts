import asyncio
import json
from datetime import datetime

import discord
import pytest
from discord.ext import commands

import stockalerts
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
class FakeChannel:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)


def run_check(tmp_path, monkeypatch, initial_alerts, prices, runs=1, fail_tickers=()):
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
