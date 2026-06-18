import asyncio
import discord
from discord.ext import commands

from utils.config import (
    ATERNOS_TARGET_SERVER, is_valid_server_name, is_on_cooldown, is_owner, COOLDOWN_SECONDS,
)
from utils.progress import make_progress_bar
from utils.minecraft_ping import get_minecraft_ping_status
from utils.aternos import run_aternos_action


class Minecraft(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._task_lock = asyncio.Lock()
        self._active_task: asyncio.Task | None = None
        self._active_task_name: str | None = None

    @property
    def is_processing(self) -> bool:
        return self._active_task is not None and not self._active_task.done()

    def _is_busy(self) -> bool:
        return self.is_processing

    @commands.command(name="start")
    async def start_minecraft(self, ctx: commands.Context):
        if not is_owner(ctx) and not ctx.author.guild_permissions.administrator:
            await ctx.send("Access denied.")
            return

        if is_on_cooldown(ctx.author.id):
            await ctx.send(f"Cooldown active. Wait {COOLDOWN_SECONDS}s between commands.")
            return

        if self._is_busy():
            await ctx.send(f"System busy: `!{self._active_task_name}` is already running.")
            return

        if not ATERNOS_TARGET_SERVER:
            await ctx.send("Configuration error: server name not set.")
            return

        if not is_valid_server_name(ATERNOS_TARGET_SERVER):
            await ctx.send("Configuration error: invalid server name format.")
            return

        status_msg = await ctx.send("Checking server status...")

        host = f"{ATERNOS_TARGET_SERVER}.aternos.me"
        res = await get_minecraft_ping_status(host)
        if res["status"] == "success" and res.get("online_count", 0) > 0:
            await status_msg.edit(content="Server is already online.")
            return

        async with self._task_lock:
            self._active_task_name = "start"

        await status_msg.edit(content=f"Boot sequence initialized.\n{make_progress_bar(0)}")

        proxy_url = self.bot.proxy_url

        async def start_wrapper():
            try:
                await run_aternos_action(ctx, "start", status_msg, proxy_url)
            except asyncio.CancelledError:
                print("Start task cancelled.")
                try:
                    await status_msg.edit(content="Start sequence cancelled.")
                except Exception:
                    try:
                        await ctx.send("Start sequence cancelled.")
                    except discord.HTTPException:
                        pass
                raise
            finally:
                async with self._task_lock:
                    self._active_task = None
                    self._active_task_name = None

        self._active_task = asyncio.create_task(start_wrapper())
        await status_msg.edit(content=f"Boot sequence started.\n{make_progress_bar(0)}")

    @commands.command(name="stop")
    async def stop_minecraft(self, ctx: commands.Context):
        if not is_owner(ctx) and not ctx.author.guild_permissions.administrator:
            await ctx.send("Access denied.")
            return

        if is_on_cooldown(ctx.author.id):
            await ctx.send(f"Cooldown active. Wait {COOLDOWN_SECONDS}s between commands.")
            return

        if self._is_busy() and self._active_task_name == "stop":
            await ctx.send("A stop action is already running.")
            return

        if not ATERNOS_TARGET_SERVER:
            await ctx.send("Configuration error: server name not set.")
            return

        if self._active_task and not self._active_task.done() and self._active_task_name == "start":
            await ctx.send("Cancelling startup to route stop sequence...")
            self._active_task.cancel()
            try:
                await asyncio.wait_for(self._active_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            async with self._task_lock:
                self._active_task = None
                self._active_task_name = None

        status_msg = await ctx.send("Sending termination signal...")
        async with self._task_lock:
            self._active_task_name = "stop"

        proxy_url = self.bot.proxy_url

        async def stop_wrapper():
            try:
                await run_aternos_action(ctx, "stop", status_msg, proxy_url)
            except asyncio.CancelledError:
                print("Stop task cancelled.")
                try:
                    await status_msg.edit(content="Stop sequence cancelled.")
                except Exception:
                    try:
                        await ctx.send("Stop sequence cancelled.")
                    except discord.HTTPException:
                        pass
                raise
            finally:
                async with self._task_lock:
                    self._active_task = None
                    self._active_task_name = None

        self._active_task = asyncio.create_task(stop_wrapper())

    @commands.command(name="interrupt")
    async def interrupt_command(self, ctx: commands.Context):
        if not is_owner(ctx) and not ctx.author.guild_permissions.administrator:
            await ctx.send("Access denied.")
            return

        task_cancelled = False
        task_name = self._active_task_name or "unknown"

        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
            task_cancelled = True
            try:
                await asyncio.wait_for(self._active_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        async with self._task_lock:
            self._active_task = None
            self._active_task_name = None

        if task_cancelled:
            await ctx.send(f"**Automation Interrupted:** Cancelled the `{task_name}` task.")
        else:
            await ctx.send("**State Reset:** Reset the bot processing state.")

    @commands.command(name="status")
    async def server_status(self, ctx: commands.Context):
        if not ATERNOS_TARGET_SERVER or not is_valid_server_name(ATERNOS_TARGET_SERVER):
            await ctx.send("Server name not configured.")
            return

        host = f"{ATERNOS_TARGET_SERVER}.aternos.me"
        status_msg = await ctx.send(f"Pinging `{host}`...")
        res = await get_minecraft_ping_status(host)

        if res["status"] == "success":
            info = res["info"]
            version = res["version_name"]
            online = res.get("online_count", 0)
            maximum = res.get("max_players", 0)
            embed = discord.Embed(title="Minecraft Server Status", color=discord.Color.green())
            embed.add_field(name="Version", value=version, inline=True)
            embed.add_field(name="Players", value=f"{online}/{maximum}", inline=True)
            embed.add_field(name="Address", value=host, inline=False)
            motd = info.get("description", {}).get("text", "")
            if motd:
                embed.add_field(name="MOTD", value=motd[:1024], inline=False)
            await status_msg.edit(content=None, embed=embed)
        else:
            await status_msg.edit(content=f"Could not reach server: {res.get('error', 'Unknown error')}")

    @commands.command(name="server")
    async def server_info(self, ctx: commands.Context):
        if not ATERNOS_TARGET_SERVER:
            await ctx.send("No server configured.")
            return
        await ctx.send(f"**{ATERNOS_TARGET_SERVER}** — `{ATERNOS_TARGET_SERVER}.aternos.me`")


async def setup(bot: commands.Bot):
    await bot.add_cog(Minecraft(bot))
