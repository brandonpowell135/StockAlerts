# StockAlerts

A Discord bot for stock price/percent alerts and quick backtests, plus a standalone
script for backtesting an S&P / 3x-leveraged (UPRO) portfolio.

## Commands

| Command | What it does |
| --- | --- |
| `/setalertprice <ticker> <target_price>` | Alert when the stock drops to the price. Fires once, then is removed. |
| `/setalertpercent <ticker> <target_percent>` | Alert on a daily move: negative for a drop (`-5`), positive for a gain (`5`). Recurring, at most once per trading day. |
| `/setalertsma <ticker> <window> <direction>` | Alert when the price crosses its 20/50/100/200-day moving average, above or below. |
| `/setalertrsi <ticker> <direction> [threshold]` | Alert when RSI(14) crosses a level: below 30 (oversold) or above 70 (overbought) by default. |
| `/myalerts` | List your alerts, numbered. |
| `/removealert <number>` | Remove one alert by its number in `/myalerts`. |
| `/removealerts` | Remove all your alerts. |
| `/quote <ticker>` | Price, daily move, day range, 50/200-day moving averages and RSI. |
| `/watchlist add\|remove\|show <ticker>` | The server's shared watchlist (up to 25 tickers). |
| `/backtest <ticker> <drop_percent> <start_date>` | Buy $100 every day the stock falls `drop_percent`% or more since `start_date` (YYYY-MM-DD), compared with buy-and-hold. |
| `!bothelp` | Help, with attitude. |
| `!pp` | Random message. |

Alerts are checked every 15 minutes (`CHECK_INTERVAL_MINUTES`) during US market hours.
Moving-average and RSI alerts fire when the line is *crossed* (not every day it stays past
it), at most once per trading day. Every weekday at 4:10pm ET the bot posts a recap of the
watchlist's closing moves in the alert channel (skipped on market holidays).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # then fill in DISCORD_TOKEN and DISCORD_CHANNEL_ID
python main.py
```

Environment variables:

| Variable | Required | Notes |
| --- | --- | --- |
| `DISCORD_TOKEN` | yes | Bot token from the Discord Developer Portal. Never commit it. |
| `DISCORD_CHANNEL_ID` | yes | Channel where alerts are posted. |
| `DISCORD_GUILD_ID` | no | Sync slash commands to this server instantly (global sync can be slow). |
| `ALERTS_FILE` | no | Defaults to `data/alerts.json`. |
| `WATCHLIST_FILE` | no | Defaults to `data/watchlist.json`. |
| `CHECK_INTERVAL_MINUTES` | no | Defaults to `15`. |

## Docker

CI builds and pushes `ghcr.io/brandonpowell135/stockalertbot:latest` on every push to `main`
(after the tests pass). To run it, mount a volume at `/app/data` so alerts survive image updates:

```bash
docker run -d --name stockalertbot --env-file .env \
  -v stockalerts-data:/app/data \
  ghcr.io/brandonpowell135/stockalertbot:latest
```

Build locally with `docker build -t stockalertbot .`.

## Backtest script

```bash
python backtest/backtest_data.py
```

Simulates weekly $100 contributions into the S&P, a 3x daily-leveraged version (net of UPRO's
0.91% expense ratio), and a 70/30 mix rebalanced quarterly. Writes a CSV and a chart with max
drawdown, longest time underwater, and Sharpe ratio. Edit the values in `main()` to change the
dates, ticker or allocation.

## Tests

```bash
pytest
```

## Ideas / Todo

Alerts:
- [ ] Support/resistance breaks
- [x] Moving average (SMA) crossovers
- [x] RSI alerts
- [ ] MACD alerts (look at matching the TradingView MACD setup)
- [ ] Bollinger Bands
- [ ] Options imbalance / unusual activity
- [x] Remove a single alert instead of all of them
- [ ] Command to clean chat messages

Backtests:
- [ ] Buy and hold when a stock drops X% from a date
- [ ] Buy on a set schedule from a date with portfolio auto-management
- [ ] Hold SPY until UPRO drops X%, then switch to UPRO
- [ ] Buy at next day's open after a drop of 10% or more
- [ ] Graph backtests vs SPY in Discord
- [ ] Options strategies
- [ ] Cash account
- [x] Max drawdown and time to recover
- [x] Sharpe ratio

Portfolio management:
- [ ] Holding allocations; monthly allocation report

Other:
- [ ] More channels (options, long-term investing, management, general alerts, how-to)
- [ ] Look into Alpaca
- [ ] Flask website
- [x] Unit tests
- [x] Daily end-of-day recap of a watchlist
- [x] Alerts no longer get wiped when a new image is pulled (use the `/app/data` volume)
