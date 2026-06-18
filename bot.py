import os
import sys
import socket
import logging
import asyncio
import traceback

import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv(override=True)

from utils.config import DISCORD_TOKEN, MY_DISCORD_USER_ID
from utils.proxy import get_configured_proxy, sanitize_proxy_url
from cogs.ai_chat import init_gemini

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("bot")

proxy_url = get_configured_proxy()
if proxy_url:
    log.info("Proxy configured for Scrapling/Aternos: %s", sanitize_proxy_url(proxy_url))


def build_bot() -> commands.Bot:
    log.info("Connecting to Discord gateway directly (no proxy)...")
    connector = aiohttp.TCPConnector(family=socket.AF_INET)
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    bot = commands.Bot(
        command_prefix="!",
        intents=intents,
        case_insensitive=True,
        connector=connector,
    )
    bot.proxy_url = proxy_url

    @bot.event
    async def on_ready():
        log.info("Bot logged in as %s", bot.user.name)
        log.info("Serving %d guild(s).", len(bot.guilds))
        for guild in bot.guilds:
            try:
                await guild.me.edit(nick="Server")
                log.info("Set nickname to 'Server' in %s", guild.name)
            except discord.Forbidden:
                log.warning("Missing permission to change nickname in %s", guild.name)

    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return
        await bot.process_commands(message)

    return bot


async def main():
    bot = build_bot()

    async with bot:
        await bot.load_extension("cogs.minecraft")
        await bot.load_extension("cogs.ai_chat")
        await bot.load_extension("cogs.keepalive")
        init_gemini()

        retry_delay = 5
        attempt = 0
        shutdown_event = asyncio.Event()

        loop = asyncio.get_running_loop()
        import signal as sig_mod
        for s in (sig_mod.SIGINT, sig_mod.SIGTERM):
            try:
                loop.add_signal_handler(s, shutdown_event.set)
            except NotImplementedError:
                pass

        while not shutdown_event.is_set():
            attempt += 1
            log.info("Connection attempt #%d...", attempt)
            try:
                await bot.start(DISCORD_TOKEN)
                break
            except discord.LoginFailure as e:
                log.critical("Discord login failed: %s", e)
                raise
            except Exception as e:
                log.error("Disconnected on attempt #%d: %s: %s", attempt, type(e).__name__, e)
                log.info("Reconnecting in %ds...", retry_delay)
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=retry_delay)
                    break
                except asyncio.TimeoutError:
                    pass
                retry_delay = min(retry_delay * 2, 60)

        log.info("Shutting down gracefully...")
        keepalive_cog = bot.get_cog("Keepalive")
        if keepalive_cog:
            keepalive_cog.cancel_ping()


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        log.critical("DISCORD_TOKEN environment variable is not set!")
        exit(1)
    if MY_DISCORD_USER_ID == 0:
        log.warning("MY_DISCORD_USER_ID not set. Owner commands disabled.")
    asyncio.run(main())
