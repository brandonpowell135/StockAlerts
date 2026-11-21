import logging
import os
import sys

import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load .env before importing modules that read configuration at import time.
load_dotenv()

from backtest import backtest  # noqa: E402
from generalchat import general_commands  # noqa: E402
from stockalerts import setup_stock_alerts  # noqa: E402

log = logging.getLogger("stockalerts")


def require_env(name):
    value = os.getenv(name)
    if not value:
        sys.exit(f"Missing required environment variable {name} (set it in .env or the container env)")
    return value


class StockBot(commands.Bot):
    def __init__(self, channel_id, guild_id=None):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.channel_id = channel_id
        self.guild_id = guild_id

    async def setup_hook(self):
        setup_stock_alerts(self, self.channel_id)
        general_commands(self)
        backtest(self)

        # Register slash commands with Discord. Syncing to one guild is instant;
        # a global sync can take a while to show up.
        if self.guild_id:
            guild = discord.Object(id=self.guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
        else:
            synced = await self.tree.sync()
        log.info("Synced %d slash commands", len(synced))

    async def on_ready(self):
        log.info("Bot is ready as %s", self.user)


def main():
    token = require_env("DISCORD_TOKEN")
    try:
        channel_id = int(require_env("DISCORD_CHANNEL_ID"))
        guild_id = int(os.getenv("DISCORD_GUILD_ID")) if os.getenv("DISCORD_GUILD_ID") else None
    except ValueError:
        sys.exit("DISCORD_CHANNEL_ID and DISCORD_GUILD_ID must be numeric IDs")

    bot = StockBot(channel_id, guild_id)
    # root_logger=True routes our own log calls through discord.py's log handler too.
    bot.run(token, root_logger=True)


if __name__ == "__main__":
    main()
