import types

import pandas as pd


class FakeChannel:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)


class FakeInteraction:
    """Just enough of discord.Interaction for calling slash command callbacks directly."""

    def __init__(self, user_id=1):
        self.user = types.SimpleNamespace(id=user_id)
        self.messages = []
        outer = self

        class Response:
            async def defer(self):
                pass

            async def send_message(self, message):
                outer.messages.append(message)

        class Followup:
            async def send(self, message):
                outer.messages.append(message)

        self.response = Response()
        self.followup = Followup()


def make_history(closes, end="2026-11-20"):
    """Daily OHLC DataFrame ending on `end`, with High/Low around the close."""
    index = pd.bdate_range(end=end, periods=len(closes))
    closes = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame({"Open": closes, "High": closes * 1.01, "Low": closes * 0.99, "Close": closes})


def choice(value):
    return types.SimpleNamespace(value=value, name=str(value))
