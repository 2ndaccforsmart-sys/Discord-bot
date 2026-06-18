import time
import asyncio
import aiohttp
from aiohttp import web
from discord.ext import commands

from utils.config import HEALTH_SECRET, SELF_PING_URL, KEEPALIVE_PORT

_start_time = time.time()


async def handle_cloud_health_check(request: web.Request) -> web.Response:
    if HEALTH_SECRET:
        token = request.headers.get("X-Health-Token") or request.query.get("token")
        if not token or not _constant_time_compare(token, HEALTH_SECRET):
            return web.Response(status=403, text="Forbidden")
    return web.Response(text="Online", content_type="text/plain")


async def handle_health(request: web.Request) -> web.Response:
    bot = request.app.get("bot")
    uptime_secs = int(time.time() - _start_time)
    return web.json_response({
        "status": "ok",
        "uptime_seconds": uptime_secs,
        "bot_connected": bot.is_ready() if bot else False,
    })


def _constant_time_compare(val1: str, val2: str) -> bool:
    import hmac
    return hmac.compare_digest(val1.encode(), val2.encode())


class Keepalive(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._ping_task: asyncio.Task | None = None
        self._runner: web.AppRunner | None = None

    @commands.Cog.listener()
    async def on_ready(self):
        if self._runner is None:
            await self._start_server()
        if self._ping_task is None or self._ping_task.done():
            self._ping_task = asyncio.create_task(self._self_ping_loop())

    async def _start_server(self):
        try:
            app = web.Application()
            app["bot"] = self.bot
            app.router.add_get("/", handle_cloud_health_check)
            app.router.add_get("/health", handle_health)
            self._runner = web.AppRunner(app)
            await self._runner.setup()
            site = web.TCPSite(self._runner, "0.0.0.0", KEEPALIVE_PORT)
            await site.start()
            print(f"Keepalive server bound to port {KEEPALIVE_PORT}")
        except OSError as e:
            print(f"Keepalive server failed to start (port {KEEPALIVE_PORT} may be in use): {e}")
        except Exception as e:
            print(f"Keepalive server error: {e}")

    async def _self_ping_loop(self):
        if not SELF_PING_URL:
            return
        print(f"Self-ping loop started: {SELF_PING_URL}")
        while True:
            await asyncio.sleep(240)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(SELF_PING_URL, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        print(f"Self-ping: {resp.status}")
            except Exception as e:
                print(f"Self-ping failed: {e}")

    def cancel_ping(self):
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(Keepalive(bot))
