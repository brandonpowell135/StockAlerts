import robin_stocks.robinhood as r
import os
import pyotp

from dotenv import load_dotenv
from discord.ext import commands


# Robinhood credentials
ROBINHOOD_USERNAME = os.getenv("ROBINHOOD_USERNAME")
ROBINHOOD_PASSWORD = os.getenv("ROBINHOOD_PASSWORD")
TOTP_SECRET = os.getenv("TOTP_SECRET")

# Login to Robinhood
def login_to_robinhood():
    try:
        totp = pyotp.TOTP(TOTP_SECRET)
        two_factor_code = totp.now()
        print(f"Generated TOTP Code: {two_factor_code}")  # Debug the TOTP code

        login_response = r.authentication.login(
            username=ROBINHOOD_USERNAME,
            password=ROBINHOOD_PASSWORD,
            mfa_code=two_factor_code
        )
        return True
    except Exception as e:
        print(f"Login failed: {e}")
        return False

# Setup portfolio command
def portfolio_managment(bot: commands.Bot):
    @bot.command()
    async def holdings(ctx):  # Added 'ctx' parameter here
        try:
            # Fetch holdings
            holdings = r.build_holdings()
            if not holdings:
                await ctx.send("Your portfolio is empty!")
                return

            # Format portfolio data
            message = "**Your Robinhood Portfolio:**\n\n"
            for stock, data in holdings.items():
                quantity = float(data['quantity'])
                price = float(data['price'])
                equity = float(data['equity'])
                percentage = float(data['percent_change'])

                message += (
                    f"**{stock}**\n"
                    f" - Quantity: {quantity:.2f}\n"
                    f" - Price: ${price:.2f}\n"
                    f" - Equity: ${equity:.2f}\n"
                    f" - Change: {percentage:.2f}%\n\n"
                )

            # Send portfolio summary
            await ctx.send(message)
        except Exception as e:
            await ctx.send(f"Error fetching portfolio: {e}")


# Logout from Robinhood
def logout_from_robinhood():
    async def on_close():
        r.authentication.logout()
