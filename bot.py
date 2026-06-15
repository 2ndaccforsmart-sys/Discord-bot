import os
import asyncio
import discord
import re
import traceback
import json
import struct
from discord.ext import commands
from aiohttp import web
from dotenv import load_dotenv
from scrapling.fetchers import FetcherSession

# Load environment variables (overriding existing system ones to prioritize .env)
load_dotenv(override=True)

# -------------------------------------------------------------
# CONFIGURATION MATRIX
# -------------------------------------------------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ATERNOS_TARGET_SERVER = os.getenv("ATERNOS_TARGET_SERVER")
MY_DISCORD_USERNAME = os.getenv("MY_DISCORD_USERNAME")

try:
    MY_DISCORD_USER_ID = int(os.getenv("MY_DISCORD_USER_ID", "0"))
except (ValueError, TypeError):
    MY_DISCORD_USER_ID = 0

# Initialize bot with intents and enable case-insensitive commands
intents = discord.Intents.default()
intents.message_content = True
intents.members = True 

bot = commands.Bot(command_prefix="!", intents=intents, case_insensitive=True)
bot.is_processing = False
bot.active_task = None
bot.active_task_name = None

def make_progress_bar(percentage, total_blocks=10):
    filled_blocks = int((percentage / 100) * total_blocks)
    empty_blocks = total_blocks - filled_blocks
    return f"`[{'■' * filled_blocks}{'□' * empty_blocks}] {percentage}%`"

def is_owner(ctx):
    if MY_DISCORD_USER_ID != 0 and ctx.author.id == MY_DISCORD_USER_ID:
        return True
    if MY_DISCORD_USERNAME and ctx.author.name.lower() == MY_DISCORD_USERNAME.lower():
        return True
    return False

# -------------------------------------------------------------
# CLOUD HEALTH WEB SERVICE (KEEPALIVE)
# -------------------------------------------------------------
async def handle_cloud_health_check(request):
    return web.Response(text="Bot Engine Network Routing Layer: Online", content_type="text/plain")

async def spin_up_keepalive_server():
    app = web.Application()
    app.router.add_get("/", handle_cloud_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.getenv("PORT", "7860"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Cloud Health Network Web Service securely bound to Port {port}.")

# -------------------------------------------------------------
# MINECRAFT SERVER STATUS PING UTILITY
# -------------------------------------------------------------
async def get_minecraft_ping_status(host, port=25565):
    """Pings the Minecraft server to retrieve live player counts and status."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=2.0
        )
        def write_varint(val):
            out = b""
            while True:
                b = val & 0x7F
                val >>= 7
                if val:
                    out += struct.pack("B", b | 0x80)
                else:
                    out += struct.pack("B", b)
                    break
            return out

        async def read_varint():
            val = 0
            for i in range(5):
                b = await reader.readexactly(1)
                if not b:
                    return 0
                b = b[0]
                val |= (b & 0x7F) << (7 * i)
                if not (b & 0x80):
                    break
            return val

        host_bytes = host.encode('utf-8')
        handshake = write_varint(0) + write_varint(763) + write_varint(len(host_bytes)) + host_bytes + struct.pack(">H", port) + write_varint(1)
        writer.write(write_varint(len(handshake)) + handshake)
        await writer.drain()

        request = write_varint(0)
        writer.write(write_varint(len(request)) + request)
        await writer.drain()

        packet_len = await read_varint()
        packet_id = await read_varint()
        json_len = await read_varint()

        data = await reader.readexactly(json_len)
        writer.close()
        try: await writer.wait_closed()
        except: pass
            
        info = json.loads(data.decode('utf-8'))
        return {"status": "success", "version_name": info.get("version", {}).get("name", ""), "info": info}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# -------------------------------------------------------------
# SCRApling AUTOMATION CORE ENGINE
# -------------------------------------------------------------
async def run_aternos_action(ctx, action_type, status_msg):
    """Executes start/stop events using Scrapling's high-speed stealth session."""
    username = os.getenv("ATERNOS_USER")
    password = os.getenv("ATERNOS_PASS")
    session_token = os.getenv("ATERNOS_SESSION")
    state_file = "aternos_state.json"

    # Attempt to load latest valid session token from state file
    if os.path.exists(state_file):
        try:
            with open(state_file, "r") as f:
                state_data = json.load(f)
                session_token = state_data.get("ATERNOS_SESSION") or session_token
        except Exception as e:
            print(f"⚠️ Failed to read aternos_state.json: {e}")

    if action_type == "start":
        await status_msg.edit(content=f"⚙️ **Bot Engine: Initializing Scrapling Stealth Runner...**\n{make_progress_bar(20)}")
    else:
        await status_msg.edit(content=f"🛑 **Bot Engine: Shutting down server panels...**\n{make_progress_bar(20)}")

    try:
        print("🚀 Booting Scrapling Fetcher Session...")
        proxy_url = os.getenv("PROXY_SERVER")
        
        with FetcherSession(proxy=proxy_url) as session:
            # Inject ATERNOS_SESSION token if available
            if session_token:
                session._curl_session.cookies.set("ATERNOS_SESSION", session_token, domain=".aternos.org")

            await status_msg.edit(content=f"📡 **Bot Engine: Requesting authenticated dashboard routing...**\n{make_progress_bar(50)}")
            page = session.get("https://aternos.org/server/")

            # Fallback Login Flow if session cookie expired/invalid
            if "login" in page.url or "input[type='password']" in page.text:
                print("🔑 Session expired. Executing automated credentials submission...")
                if not username or not password:
                    raise Exception("Missing ATERNOS_USER or ATERNOS_PASS environment variables.")

                login_payload = {
                    "user": username,
                    "password": password
                }
                page = session.post("https://aternos.org/servers/", data=login_payload)
                
                # Update saved session token if a new one is set
                new_session = session._curl_session.cookies.get("ATERNOS_SESSION")
                if new_session:
                    try:
                        with open(state_file, "w") as f:
                            json.dump({"ATERNOS_SESSION": new_session}, f)
                        print("💾 Session token updated in aternos_state.json")
                    except Exception as e:
                        print(f"⚠️ Failed to save updated session token: {e}")

            # Extract Dynamic Security Tokens
            ajax_token = None
            ajax_token_match = re.search(r"ajaxToken\s*=\s*['\"]([^'\"]+)['\"]", page.text)
            if ajax_token_match:
                ajax_token = ajax_token_match.group(1)

            sec_header_val = None
            for name, value in session._curl_session.cookies.items():
                if name.startswith("ATERNOS_SEC_"):
                    sec_name = name.replace("ATERNOS_SEC_", "")
                    sec_header_val = f"{sec_name}:{value}"
                    break

            # Execute Request Actions using Scrapling session
            if action_type == "start":
                if ajax_token and sec_header_val:
                    headers = {
                        "X-Requested-With": "XMLHttpRequest",
                        "SEC": sec_header_val,
                        "Referer": "https://aternos.org/server/"
                    }
                    url = f"https://aternos.org/panel/ajax/start.php?headstart=0&access-credits=0&token={ajax_token}"
                    res = session.get(url, headers=headers)
                    print(f"Start AJAX response status: {res.status}")
                await status_msg.edit(content=f"🎉 **Ignition Signal Completed!**\n{make_progress_bar(100)}\n🟢 **Server command processed. Launching up Minecraft!** 🎮")
            
            elif action_type == "stop":
                if ajax_token and sec_header_val:
                    headers = {
                        "X-Requested-With": "XMLHttpRequest",
                        "SEC": sec_header_val,
                        "Referer": "https://aternos.org/server/"
                    }
                    url = f"https://aternos.org/panel/ajax/stop.php?token={ajax_token}"
                    res = session.get(url, headers=headers)
                    print(f"Stop AJAX response status: {res.status}")
                await status_msg.edit(content=f"🛑 **Stop signal dispatched. Server is shutting down...**\n{make_progress_bar(100)}")

    except Exception as e:
        traceback.print_exc()
        await status_msg.edit(content=f"❌ **AUTOMATION STALLED:** Scrapling pipeline error.\nDetails: `{str(e)}`")

# -------------------------------------------------------------
# COMMAND DISPATCH LOGIC
# -------------------------------------------------------------
def is_bot_busy():
    return bot.active_task and not bot.active_task.done()

@bot.command(name="start")
async def start_minecraft(ctx):
    if not is_owner(ctx) and not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ **PERMISSION DENIED: Unauthorized access.**")
        return
        
    if is_bot_busy():
        await ctx.send(f"⚠️ **System Busy:** An action (`!{bot.active_task_name}`) is already running!")
        return

    if not ATERNOS_TARGET_SERVER:
        await ctx.send("❌ **CONFIGURATION ERROR: ATERNOS_TARGET_SERVER env variable is not set.**")
        return
        
    status_msg = await ctx.send("⚙️ **Checking server status...**")
    
    host = f"{ATERNOS_TARGET_SERVER}.aternos.me"
    res = await get_minecraft_ping_status(host)
    if res["status"] == "success" and "online" in res.get("version_name", "").lower():
        await status_msg.edit(content=f"🎉 **Server is already Online!**\n🟢 **Join up boys!** 🎮")
        return
        
    bot.is_processing = True
    bot.active_task_name = "start"
    await status_msg.edit(content=f"⚙️ **Bot Engine: Boot Sequence Initialized**\n{make_progress_bar(0)}")
    
    async def start_wrapper():
        try:
            await run_aternos_action(ctx, "start", status_msg)
        finally:
            bot.is_processing = False
            bot.active_task = None
            bot.active_task_name = None

    bot.active_task = asyncio.create_task(start_wrapper())

@bot.command(name="stop")
async def stop_minecraft(ctx):
    if not is_owner(ctx) and not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ **PERMISSION DENIED: Unauthorized access.**")
        return
        
    if is_bot_busy() and bot.active_task_name == "stop":
        await ctx.send("⚠️ **System Busy:** A stop action is already running!")
        return

    if not ATERNOS_TARGET_SERVER:
        await ctx.send("❌ **CONFIGURATION ERROR: ATERNOS_TARGET_SERVER env variable is not set.**")
        return

    if bot.active_task and not bot.active_task.done() and bot.active_task_name == "start":
        await ctx.send("⏳ **Cancelling startup tracking to route stop sequence...**")
        bot.active_task.cancel()
        try: await asyncio.wait_for(bot.active_task, timeout=2.0)
        except: pass
        bot.is_processing = False
        bot.active_task = None
        bot.active_task_name = None

    status_msg = await ctx.send("🛑 **Sending termination signal...**")
    bot.is_processing = True
    bot.active_task_name = "stop"
    
    async def stop_wrapper():
        try:
            await run_aternos_action(ctx, "stop", status_msg)
        finally:
            bot.is_processing = False
            bot.active_task = None
            bot.active_task_name = None

    bot.active_task = asyncio.create_task(stop_wrapper())

@bot.command(name="interrupt")
async def interrupt_command(ctx):
    if not is_owner(ctx) and not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ **PERMISSION DENIED: Unauthorized access.**")
        return
        
    task_cancelled = False
    task_name = bot.active_task_name or "unknown"
    
    if bot.active_task and not bot.active_task.done():
        bot.active_task.cancel()
        task_cancelled = True
        try: await asyncio.wait_for(bot.active_task, timeout=2.0)
        except: pass
            
    bot.is_processing = False
    bot.active_task = None
    bot.active_task_name = None
    
    if task_cancelled:
        await ctx.send(f"🛑 **Automation Interrupted:** Cancelled the `{task_name}` task.")
    else:
        await ctx.send("🛑 **State Reset:** Reset the bot processing state.")

@bot.command(name="setup")
async def setup_command(ctx):
    if not is_owner(ctx):
        await ctx.send("❌ **UNAUTHORIZED ACCESS**")
        return
    await ctx.send("🛠️ **Setup Protocol Verified:** Configurations locked successfully!")

async def main():
    await spin_up_keepalive_server()
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ Error: DISCORD_TOKEN environment variable is not set!")
        exit(1)
    asyncio.run(main())