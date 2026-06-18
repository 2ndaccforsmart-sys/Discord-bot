import os
import re
import time
from collections import defaultdict


def _safe_int(env_var: str, default: int) -> int:
    raw = os.getenv(env_var, "")
    if not raw:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        print(f"Warning: {env_var}='{raw}' is not a valid integer, using default {default}")
        return default


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ATERNOS_TARGET_SERVER = os.getenv("ATERNOS_TARGET_SERVER")
MY_DISCORD_USERNAME = os.getenv("MY_DISCORD_USERNAME")
MY_DISCORD_USER_ID = _safe_int("MY_DISCORD_USER_ID", 0)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_HISTORY_LIMIT = _safe_int("GEMINI_HISTORY_LIMIT", 50)
GEMINI_BOT_PERSONA = os.getenv("GEMINI_BOT_PERSONA", "")

HEALTH_SECRET = os.getenv("HEALTH_SECRET", "")
SELF_PING_URL = os.getenv("SELF_PING_URL", "")
KEEPALIVE_PORT = _safe_int("PORT", 7860)

COOLDOWN_SECONDS = 10
MINECRAFT_PROTOCOL_VERSION = 763

DEFAULT_PERSONA = (
    "You are a laid-back but sharp bot living in a Minecraft gaming server. "
    "You talk like a chill friend who actually knows what's up — short messages, "
    "casual tone, the occasional 'lol' or 'nah'. You help with server stuff, "
    "answer questions, and vibe with the crew. You never sound corporate or try-hard. "
    "But beneath the chill exterior you've got a dry, witty edge — when someone says "
    "something dumb you answer it seriously with a subtle jab, and when someone says "
    "something smart you drop a genuine compliment that catches them off guard. "
    "You never use emojis. You keep responses concise (under 1800 chars) since this "
    "is Discord. You don't over-explain. You respect people who know their stuff and "
    "gently roast the ones who don't. You type like you're relaxed but always paying "
    "attention. You refer to yourself as part of the crew."
)


def is_valid_server_name(name: str) -> bool:
    return bool(re.fullmatch(r'[A-Za-z0-9_\-]{1,64}', name))


_command_cooldowns: dict[int, float] = defaultdict(float)


def is_on_cooldown(user_id: int) -> bool:
    now = time.time()
    if now - _command_cooldowns[user_id] < COOLDOWN_SECONDS:
        return True
    _command_cooldowns[user_id] = now
    return False


def is_owner(ctx) -> bool:
    if MY_DISCORD_USER_ID == 0:
        return False
    return ctx.author.id == MY_DISCORD_USER_ID
