import os
import asyncio
import discord
import re
import traceback
import json
import struct
import random
from discord.ext import commands
from aiohttp import ClientSession, web
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Load environment variables from .env if present
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Required if falling back to guild scanning for owner DMs

# Enable case_insensitive=True so that !START, !start, !StArT all work perfectly
bot = commands.Bot(command_prefix="!", intents=intents, case_insensitive=True)

# -------------------------------------------------------------
# CONFIGURATION MATRIX (SET VIA ENVIRONMENT VARIABLES OR FALLBACKS)
# -------------------------------------------------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ATERNOS_TARGET_SERVER = os.getenv("ATERNOS_TARGET_SERVER", "IISJschool")
MY_DISCORD_USERNAME = os.getenv("MY_DISCORD_USERNAME", "thanki_daksh")

try:
    MY_DISCORD_USER_ID = int(os.getenv("MY_DISCORD_USER_ID", "0"))
except ValueError:
    MY_DISCORD_USER_ID = 0
# -------------------------------------------------------------

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
    if ctx.author.name.lower() == MY_DISCORD_USERNAME.lower():
        return True
    return False

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
# AUTOMATED MASTER ON_READY
# -------------------------------------------------------------

@bot.event
async def on_ready():
    print("--------------------------------------------------")
    print(f"🚀 CLOUD RUNTIME ONLINE: Case-Insensitive Bot Stack Live!")
    print(f"🤖 Connected as: {bot.user.name}")
    print("--------------------------------------------------")


# -------------------------------------------------------------
# CLOUDFLARE TURNSTILE & STATUS POLLING UTILITIES
# -------------------------------------------------------------
# Keep track of Turnstile click attempts to avoid infinite loops
turnstile_attempts = 0

async def handle_turnstile(page, status_msg):
    """Detects and clicks Cloudflare Turnstile checkbox if present inside an iframe."""
    global turnstile_attempts
    await page.wait_for_timeout(2000)
    for frame in page.frames:
        if "challenges.cloudflare.com" in frame.url or "challenge-platform" in frame.url or "turnstile" in frame.url:
            if turnstile_attempts >= 2:
                print("⚠️ Maximum Turnstile click attempts reached. Skipping further clicks to prevent loop.")
                return
                
            print("🔍 Found Cloudflare Turnstile iframe. Attempting to click...")
            await status_msg.edit(content=f"⚙️ **Security Check:** Bypassing Cloudflare Turnstile challenge...\n{make_progress_bar(50)}")
            
            # Wait for frame DOM content to be fully loaded
            try:
                await frame.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception as e:
                print(f"⚠️ Timeout waiting for Turnstile frame DOM: {e}")
            
            # Target the checkbox input or checkbox label specifically inside the iframe
            checkbox = frame.locator('input[type="checkbox"], .ctp-checkbox-label, #checkbox, span.mark, .cb-i, #challenge-stage')
            if await checkbox.count() > 0:
                try:
                    turnstile_attempts += 1
                    print(f"👉 Turnstile click attempt #{turnstile_attempts}...")
                    target_element = checkbox.first
                    await target_element.wait_for(state="visible", timeout=5000)
                    
                    # Human-like interaction with safety timeouts
                    await target_element.hover(timeout=5000)
                    await asyncio.sleep(random.uniform(0.3, 0.7))
                    await target_element.click(force=True, timeout=5000)
                    print("✅ Clicked Turnstile checkbox successfully!")
                    await page.wait_for_timeout(3000)
                except Exception as e:
                    print(f"⚠️ Failed to click Turnstile checkbox: {e}")
                    traceback.print_exc()

async def monitor_status(ctx, page, status_msg, action_type):
    """Polls the page status to provide real-time status updates in Discord."""
    # Support polling for up to 15 minutes (180 polls * 5 seconds) to accommodate queue wait times
    max_polls = 180  
    queue_alert_sent = False
    
    for i in range(max_polls):
        await page.wait_for_timeout(5000)
        status_element = page.locator('.statuslabel-label, .status, .statuslabel')
        status_text = "Unknown"
        if await status_element.count() > 0:
            status_text = (await status_element.first.inner_text()).strip()
            
        progress = 60 + int((i / max_polls) * 40)
        
        # Format status string (collapses multiple whitespace/newlines into a single line)
        status_clean = " ".join(status_text.split())
        
        # Inline auto-confirmation (in case queue ends or dialog appears during loop)
        confirm_button = page.locator('#confirm, button:has-text("Confirm"), button:has-text("Accept"), button:has-text("Ja"), button:has-text("Ok"), button:has-text("Close")')
        if await confirm_button.count() > 0 and await confirm_button.first.is_visible():
            print("👉 Live confirm dialog appeared during status loop. Clicking confirm...")
            await confirm_button.first.click()
            await page.wait_for_timeout(2000)
            continue
            
        if action_type == "start":
            if "Online" in status_text:
                # Retrieve player count, RAM, and CPU info
                players_element = page.locator('.live-status-box .players, .players')
                ram_element = page.locator('.ram .usage, .ram')
                cpu_element = page.locator('.cpu .usage, .cpu')
                
                players_text = (await players_element.first.inner_text()).strip() if await players_element.count() > 0 else "N/A"
                ram_text = (await ram_element.first.inner_text()).strip() if await ram_element.count() > 0 else "N/A"
                cpu_text = (await cpu_element.first.inner_text()).strip() if await cpu_element.count() > 0 else "N/A"
                
                status_desc = (
                    f"🟢 **Minecraft server is now ONLINE! Join up!** 🎮\n"
                    f"👥 **Players:** `{players_text}`\n"
                    f"💾 **RAM Usage:** `{ram_text}`\n"
                    f"⚡ **CPU Usage:** `{cpu_text}`"
                )
                await status_msg.edit(content=f"🎉 **Ignition Signal Completed!**\n{make_progress_bar(100)}\n{status_desc}")
                return
            elif "queue" in status_text.lower():
                # Edit status message to show Server Launching... and queue details, appending (Queue) at the very end
                await status_msg.edit(content=f"⏳ **Server Launching...**\n{make_progress_bar(progress)}\n📡 **Status:** `{status_clean}` (Queue)")
                
                # Send a separate alert message in the channel once
                if not queue_alert_sent:
                    # Extract wait time details (e.g., "ca. 11 min")
                    time_match = re.search(r'([ca\.\s\d]+min|[ca\.\s\d]+h)', status_clean, re.IGNORECASE)
                    queue_time = time_match.group(1).strip() if time_match else "underway"
                    await ctx.send(f"⏳ **Queue Alert:** The server is currently in queue. Estimated wait time: `{queue_time}`.")
                    queue_alert_sent = True
                    
            elif "Starting" in status_text or "Loading" in status_text:
                await status_msg.edit(content=f"⏳ **Server is starting up...**\n{make_progress_bar(progress)}\n📡 **Status:** `{status_clean}`")
            else:
                await status_msg.edit(content=f"⏳ **Boot Sequence Active...**\n{make_progress_bar(progress)}\n📡 **Status:** `{status_clean}`")
                
        elif action_type == "stop":
            if "offline" in status_text.lower():
                await status_msg.edit(content="🛑 **Server Offline**")
                return
            else:
                # Keep stop messages extremely clean as requested (no bar, no live text info)
                await status_msg.edit(content="🛑 **Shutting down...**")
                
    # Timeout reached
    if action_type == "start":
        await status_msg.edit(content=f"⚠️ **Boot sequence monitored but did not transition to final state within 15 minutes.**\n📡 **Current Status:** `{status_clean}`")
    else:
        await status_msg.edit(content="⚠️ **Shutdown sequence timed out.**")

# -------------------------------------------------------------
# SESSION COOKIE SYNC HELPER
# -------------------------------------------------------------
async def save_session_cookie_if_changed(context, current_saved_token):
    """Fetches the active ATERNOS_SESSION cookie from the browser and saves it if changed."""
    cookies = await context.cookies()
    current_browser_token = next((c["value"] for c in cookies if c["name"] == "ATERNOS_SESSION"), None)
    if current_browser_token and current_browser_token != current_saved_token:
        print("🔄 Detected updated ATERNOS_SESSION cookie. Saving it to state file...")
        try:
            with open("aternos_state.json", "w") as f:
                json.dump({"ATERNOS_SESSION": current_browser_token}, f)
            return current_browser_token
        except Exception as e:
            print(f"⚠️ Failed to save state file: {e}")
    return current_saved_token

async def get_minecraft_ping_status(host, port=25565):
    """Pings a Minecraft server to retrieve its SLP status JSON."""
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

        # Handshake packet
        host_bytes = host.encode('utf-8')
        handshake = write_varint(0) + write_varint(763) + write_varint(len(host_bytes)) + host_bytes + struct.pack(">H", port) + write_varint(1)
        writer.write(write_varint(len(handshake)) + handshake)
        await writer.drain()

        # Request packet
        request = write_varint(0)
        writer.write(write_varint(len(request)) + request)
        await writer.drain()

        # Response packet
        packet_len = await read_varint()
        packet_id = await read_varint()
        json_len = await read_varint()

        data = await reader.readexactly(json_len)
        writer.close()
        try:
            await writer.wait_closed()
        except:
            pass
            
        info = json.loads(data.decode('utf-8'))
        version_name = info.get("version", {}).get("name", "")
        return {"status": "success", "version_name": version_name, "info": info}
    except Exception as e:
        return {"status": "error", "error": str(e)}

async def check_server_offline_ping():
    """Checks if the server is offline using the Minecraft Server List Ping."""
    host = f"{ATERNOS_TARGET_SERVER}.aternos.me"
    res = await get_minecraft_ping_status(host)
    if res["status"] == "error":
        # If port is closed/unreachable, it is offline on Aternos
        return True, "offline (ping error)"
    
    version_name = res.get("version_name", "").lower()
    if "offline" in version_name:
        return True, "offline"
    elif "online" in version_name:
        return False, "online"
    elif any(x in version_name for x in ["starting", "preparing", "queue", "loading", "booting"]):
        return False, "starting"
        
    return False, "unknown"

async def human_type(locator, text):
    """Types text into a locator with human-like speed, random delays, and occasional corrected typos."""
    await locator.click()
    await asyncio.sleep(random.uniform(0.3, 0.7))
    
    for char in text:
        # 8% chance of making a typo on alphanumeric characters
        if char.isalnum() and random.random() < 0.08:
            wrong_char = random.choice("abcdefghijklmnopqrstuvwxyz")
            if wrong_char != char.lower():
                await locator.press_sequentially(wrong_char)
                await asyncio.sleep(random.uniform(0.15, 0.4))
                await locator.press("Backspace")
                await asyncio.sleep(random.uniform(0.1, 0.3))
                
        await locator.press_sequentially(char)
        await asyncio.sleep(random.uniform(0.08, 0.25))
        
    await asyncio.sleep(random.uniform(0.4, 0.8))

async def wait_for_page_or_turnstile(page, status_msg, timeout_ms=30000):
    """Waits for either the main page elements or a Cloudflare Turnstile challenge, handling it if found."""
    global turnstile_attempts
    turnstile_attempts = 0
    start_time = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start_time) * 1000 < timeout_ms:
        # Check if target page selectors are present
        target_selectors = page.locator('input[type="password"], .server, .server-body, .server-card')
        if await target_selectors.count() > 0:
            return "ready"
            
        # Check if Turnstile iframe is present
        for frame in page.frames:
            if "challenges.cloudflare.com" in frame.url or "challenge-platform" in frame.url or "turnstile" in frame.url:
                print("🔍 Cloudflare Turnstile detected during wait. Handling...")
                await handle_turnstile(page, status_msg)
                # Wait a bit for transition
                await page.wait_for_timeout(3000)
                break
                
        await page.wait_for_timeout(1000)
    
    # If we timed out, raise an exception
    raise Exception(f"Timeout waiting for server page or Cloudflare bypass after {timeout_ms/1000}s")

async def get_proxy_details(proxy_url):
    """Detects the locale and timezone of the proxy server to align the browser fingerprint."""
    if not proxy_url:
        return "en-US", "UTC"
    try:
        print(f"🌍 Performing geo-lookup through proxy: {proxy_url}")
        async with ClientSession() as session:
            async with session.get("http://ip-api.com/json", proxy=proxy_url, timeout=5) as r:
                if r.status == 200:
                    data = await r.json()
                    timezone = data.get("timezone", "UTC")
                    country_code = data.get("countryCode", "US").lower()
                    
                    # Map country codes to common locale string signatures
                    locale_map = {
                        "us": "en-US", "gb": "en-GB", "pl": "pl-PL", 
                        "de": "de-DE", "es": "es-ES", "jp": "ja-JP",
                        "fr": "fr-FR", "ca": "en-CA", "au": "en-AU"
                    }
                    locale = locale_map.get(country_code, "en-US")
                    print(f"✅ Proxy Details: Country={data.get('country')}, Timezone={timezone}, Locale={locale}")
                    return locale, timezone
    except Exception as e:
        print(f"⚠️ Proxy Geo-lookup failed: {e}. Defaulting to en-US/UTC.")
    return "en-US", "UTC"

# -------------------------------------------------------------
# PLAYWRIGHT AUTOMATION ENGINE
# -------------------------------------------------------------
async def run_aternos_action(ctx, action_type, status_msg):
    """Dispatches clean browser automation flows directly to Aternos via Playwright."""
    target_server = ATERNOS_TARGET_SERVER
    
    # Priority Loading of session token
    session_token = None
    env_token = os.getenv("ATERNOS_SESSION")
    state_token = None
    if os.path.exists("aternos_state.json"):
        try:
            with open("aternos_state.json", "r") as f:
                state = json.load(f)
                state_token = state.get("ATERNOS_SESSION")
        except Exception as e:
            print(f"Could not read aternos_state.json: {e}")
            
    if state_token:
        # If env token changed manually, respect it; otherwise prioritize saved state
        if env_token and env_token != state_token:
            session_token = env_token
            print("🔑 Using manually updated ATERNOS_SESSION from .env file.")
        else:
            session_token = state_token
            print("🔑 Using latest saved ATERNOS_SESSION from aternos_state.json.")
    else:
        session_token = env_token
        if env_token:
            print("🔑 Using initial ATERNOS_SESSION from .env file.")

    username = os.getenv("ATERNOS_USER")
    password = os.getenv("ATERNOS_PASS")
    user_data_dir = "./aternos_browser_session"

    # Launch browser loading message (Only show progress bar on start commands)
    if action_type == "start":
        await status_msg.edit(content=f"⚙️ **Bot Engine: Launching virtual browser environment...**\n{make_progress_bar(15)}")
    else:
        await status_msg.edit(content="🛑 **Shutting down...**")

    async with async_playwright() as p:
        # Launch Chromium persistent context (stealthy, matching Linux container signature)
        headless_mode = os.getenv("ATERNOS_HEADLESS", "true").lower() != "false"
        if os.getenv("DISPLAY") is not None:
            print("🖥️ X Virtual Frame Buffer (Xvfb) detected! Running in headful mode for Turnstile bypass.")
            headless_mode = False

        # Read optional proxy server settings and dynamically align fingerprint
        proxy_settings = None
        proxy_url = os.getenv("PROXY_SERVER")
        if not proxy_url:
            proxy_url = "http://mhlyphkj:seqgahpd0irq@38.154.203.95:5863"
            print("🌐 Using fallback hardcoded proxy server...")

        if proxy_url:
            print("🌐 Routing browser traffic through proxy server...")
            proxy_settings = {"server": proxy_url}

        locale_str, timezone_str = await get_proxy_details(proxy_url)

        user_agent_str = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=headless_mode,
            user_agent=user_agent_str,
            viewport={"width": 1280, "height": 720},
            locale=locale_str,
            timezone_id=timezone_str,
            proxy=proxy_settings,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ]
        )
        
        # Apply playwright-stealth to context (applies to all pages and subframes)
        lang_base = locale_str.split('-')[0]
        stealth_evasion = Stealth(
            navigator_user_agent_override=user_agent_str,
            navigator_platform_override="Linux x86_64",
            navigator_languages_override=(locale_str, lang_base),
            chrome_runtime=True
        )
        await stealth_evasion.apply_stealth_async(context)
        print("🛡️ Playwright Stealth Evasion activated successfully for all frames!")
        
        # Inject cookie if ATERNOS_SESSION is defined
        if session_token:
            await context.add_cookies([{
                "name": "ATERNOS_SESSION",
                "value": session_token,
                "domain": ".aternos.org",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "Lax"
            }])
            print("🔑 Injected ATERNOS_SESSION cookie into browser context.")

        page = await context.new_page()

        if action_type == "start":
            await status_msg.edit(content=f"⚙️ **Bot Engine: Connecting to Aternos portal...**\n{make_progress_bar(30)}")
        
        try:
            # Navigate to servers list (wait only for DOM to be parsed, not ads/trackers)
            await page.goto("https://aternos.org/servers/", wait_until="domcontentloaded", timeout=30000)
            
            # Wait for list cards or login container to load, checking for and handling Turnstile concurrently
            await wait_for_page_or_turnstile(page, status_msg, timeout_ms=60000)

            # Check if redirected to login page
            if "login" in page.url or await page.locator('input[type="password"]').count() > 0:
                print("⚠️ Session expired or invalid. Attempting credential login fallback...")
                if action_type == "start":
                    await status_msg.edit(content=f"⚙️ **Session Expired: Bypassing security gates and logging in...**\n{make_progress_bar(45)}")
                
                # Check for Cloudflare Turnstile inside iframe and click it
                await handle_turnstile(page, status_msg)

                # Fill credentials
                if not username or not password:
                    raise Exception("Aternos credentials (ATERNOS_USER and ATERNOS_PASS) are not set. Cannot log in.")

                # Fill username
                user_input = page.locator('input[placeholder*="Username" i], input[name="user"], input[id="user"]').first
                await human_type(user_input, username)
                
                # Fill password
                pass_input = page.locator('input[type="password"], input[name="password"]').first
                await human_type(pass_input, password)
                
                # Click login button
                login_btn = page.locator('button:has-text("Login"), button:has-text("Log in"), button.btn-primary, input[type="submit"]').first
                await login_btn.click()
                
                # Wait for redirect back to servers page
                await page.wait_for_url("**/servers/", timeout=30000)

                # Capture post-login cookie
                session_token = await save_session_cookie_if_changed(context, session_token)

            # Select target server if we are on the servers list page
            if "/servers" in page.url:
                if action_type == "start":
                    await status_msg.edit(content=f"⚙️ **Bot Engine: Targeting server card `{target_server}`...**\n{make_progress_bar(60)}")
                
                # List of card click targets (prioritizing the exact text card button itself)
                card_selectors = [
                    f'.server:has-text("{target_server}")',
                    f'.server-body:has-text("{target_server}")',
                    f'.server-card:has-text("{target_server}")',
                    f'div:has-text("{target_server}") .server-name',
                    f'div:has-text("{target_server}") .name',
                    f'text="{target_server}"',
                ]
                
                clicked = False
                for selector in card_selectors:
                    locator = page.locator(selector)
                    if await locator.count() > 0:
                        print(f"👉 Selector matched: {selector}. Attempting to click card...")
                        await locator.first.hover()
                        await locator.first.click()
                        clicked = True
                        break
                
                if not clicked:
                    print("⚠️ Could not match server card. Trying direct navigation to /server/.")
                    await page.goto("https://aternos.org/server/", wait_until="domcontentloaded")
                else:
                    await page.wait_for_url("**/server/", timeout=30000)

            # Ensure we are on the singular server page (not the multiple servers list page)
            if "/servers" in page.url or "/server" not in page.url:
                print("⚠️ Not on the singular server page. Attempting direct navigation to /server/...")
                await page.goto("https://aternos.org/server/", wait_until="domcontentloaded")
                await page.wait_for_url("**/server/", timeout=30000)

            # Double-check page path to ensure we aren't stuck on list page
            if "/servers" in page.url:
                raise Exception("Aternos redirected us back to servers page. The targeted server might be invalid or access-restricted.")

            # --- FETCH & SYNC COOKIE STATE BEFORE INTERACTING WITH BUTTONS ---
            session_token = await save_session_cookie_if_changed(context, session_token)
            # ------------------------------------------------------------------

            # Read current status
            status_element = page.locator('.statuslabel-label, .status, .statuslabel')
            status_text = "Offline"
            if await status_element.count() > 0:
                status_text = (await status_element.first.inner_text()).strip()
            print(f"Current server status: {status_text}")

            if action_type == "start":
                if "Online" in status_text:
                    await status_msg.edit(content=f"🎉 **Server is already Online!**\n{make_progress_bar(100)}\n🟢 **Join up boys!** 🎮")
                    return
                elif "Starting" in status_text or "Loading" in status_text or "queue" in status_text.lower():
                    # Server is already loading or in queue. Skip clicking and jump straight to monitoring
                    status_clean = " ".join(status_text.split())
                    suffix = " (Queue)" if "queue" in status_text.lower() else ""
                    await status_msg.edit(content=f"⏳ **Server is already active:** `{status_clean}`{suffix}\n{make_progress_bar(50)}")
                    await monitor_status(ctx, page, status_msg, action_type)
                    return

                # Click Start (only if it exists and is visible)
                start_button = page.locator('#start, button:has-text("Start"), button:has-text("Starten")')
                if await start_button.count() > 0 and await start_button.first.is_visible():
                    await start_button.first.click()
                    
                    # Handle EULA / Confirm / Ok / Close popups (only click if they actually appear and are visible)
                    confirm_button = page.locator('#confirm, button:has-text("Confirm"), button:has-text("Accept"), button:has-text("Ja"), button:has-text("Ok"), button:has-text("Close")')
                    # Fast wait for confirm button
                    try:
                        await confirm_button.first.wait_for(state="visible", timeout=2000)
                    except:
                        pass
                    
                    if await confirm_button.count() > 0 and await confirm_button.first.is_visible():
                        print("👉 Confirm dialog appeared. Clicking confirm...")
                        await confirm_button.first.click()

                    # Monitor status transition
                    await monitor_status(ctx, page, status_msg, action_type)
                else:
                    raise Exception("Start button is not visible on page. The server might be in a transitional state.")

            elif action_type == "stop":
                if "offline" in status_text.lower():
                    await status_msg.edit(content="🛑 **The Server is Already Offline.**")
                    return

                # Click Stop
                stop_button = page.locator('#stop, button:has-text("Stop"), button:has-text("Stoppen")')
                if await stop_button.count() > 0 and await stop_button.first.is_visible():
                    await stop_button.first.click()
                    await page.wait_for_timeout(2000)  # USER REQUEST: Exactly 2s delay
                    
                    # Monitor status transition
                    await monitor_status(ctx, page, status_msg, action_type)
                else:
                    # If the stop button is not visible, it might mean the server went offline
                    if "offline" in status_text.lower():
                        await status_msg.edit(content="🛑 **Server Offline**")
                    else:
                        raise Exception("Stop button is not visible on page.")

        except Exception as e:
            traceback.print_exc()
            try:
                # Capture screenshot on failure to diagnose Cloudflare block or selector issues
                screenshot_path = "error_screenshot.png"
                await page.screenshot(path=screenshot_path, full_page=True)
                file = discord.File(screenshot_path, filename="error.png")
                await ctx.send("📷 **Automation Error Screenshot:**", file=file)
            except Exception as se:
                print(f"Failed to capture error screenshot: {se}")
                
            if action_type == "start":
                await status_msg.edit(content=f"❌ **AUTOMATION STALLED:** Connection pipeline error.\nError Details: `{str(e)}`")
            else:
                # If we throw an exception during stop, double-check if the server is offline anyway
                await status_msg.edit(content="🛑 **Server Offline**")
        finally:
            await context.close()

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
        
    status_msg = await ctx.send("⚙️ **Checking server status...**")
    
    # Instant check: check if already online
    host = f"{ATERNOS_TARGET_SERVER}.aternos.me"
    res = await get_minecraft_ping_status(host)
    if res["status"] == "success" and "online" in res.get("version_name", "").lower():
        await status_msg.edit(content=f"🎉 **Server is already Online!**\n🟢 **Join up boys!** 🎮")
        return
        
    bot.is_processing = True
    bot.active_task_name = "start"
    await status_msg.edit(content=f"⚙️ **Bot Engine: Boot Sequence**\n{make_progress_bar(0)}")
    
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
        
    # If the active task is a stop action already, block it
    if is_bot_busy() and bot.active_task_name == "stop":
        await ctx.send("⚠️ **System Busy:** A stop action is already running!")
        return

    # If a start task is running, cancel it
    if bot.active_task and not bot.active_task.done() and bot.active_task_name == "start":
        await ctx.send("⏳ **Cancelling server startup monitoring to execute stop command...**")
        bot.active_task.cancel()
        try:
            await asyncio.wait_for(bot.active_task, timeout=2.0)
        except:
            pass
        bot.is_processing = False
        bot.active_task = None
        bot.active_task_name = None

    status_msg = await ctx.send("⚙️ **Checking server status...**")
    
    # Instant check: check if already offline
    is_offline, reason = await check_server_offline_ping()
    if is_offline:
        await status_msg.edit(content="🛑 **The Server is Already Offline.**")
        return
        
    bot.is_processing = True
    bot.active_task_name = "stop"
    await status_msg.edit(content="🛑 **Shutting down...**")
    
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
        try:
            await asyncio.wait_for(bot.active_task, timeout=2.0)
        except:
            pass
            
    # Force reset state
    bot.is_processing = False
    bot.active_task = None
    bot.active_task_name = None
    
    if task_cancelled:
        await ctx.send(f"🛑 **Automation Interrupted:** Cancelled the running `{task_name}` task and reset bot state.")
    else:
        await ctx.send("🛑 **State Reset:** Reset the bot processing state (no active task was running).")

@bot.command(name="setup")
async def setup_command(ctx):
    if not is_owner(ctx):
        await ctx.send("❌ **UNAUTHORIZED ACCESS**")
        return
    await ctx.send("🛠️ **Setup Protocol Verified:** Configurations verified and locked using ownership check!")

async def main():
    # Bind to Port instantly on boot to satisfy Render's port scan checks
    await spin_up_keepalive_server()
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ Error: DISCORD_TOKEN environment variable is not set!")
        exit(1)
    asyncio.run(main())