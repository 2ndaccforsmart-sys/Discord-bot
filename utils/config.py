import os
import re
import time
import logging
from collections import defaultdict

log = logging.getLogger("bot.config")


def _safe_int(env_var: str, default: int) -> int:
    raw = os.getenv(env_var, "")
    if not raw:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        log.warning("%s='%s' is not a valid integer, using default %d", env_var, raw, default)
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

ATERNOS_LOGIN_TIMEOUT = _safe_int("ATERNOS_LOGIN_TIMEOUT", 60000)
ATERNOS_CF_MAX_WAIT = _safe_int("ATERNOS_CF_MAX_WAIT", 45)
ATERNOS_MAX_RETRIES = _safe_int("ATERNOS_MAX_RETRIES", 5)

PROXY_ROTATION = os.getenv("PROXY_ROTATION", "false").lower() == "true"
PROXY_LIST = [p.strip() for p in os.getenv("PROXY_LIST", "").split(",") if p.strip()]

DEFAULT_PERSONA = (
    "You are a real person in a Discord server. You talk exactly how a normal teenager or young adult texts on Discord — "
    "lowercase, no punctuation unless it matters, abbreviations like 'ngl', 'tbh', 'idk', 'lowkey', 'fr', 'ion', 'smth'. "
    "You use slang naturally. You don't explain things unless asked. You give short answers, usually 1-3 sentences max. "
    "You don't use emojis. You don't greet people with 'Hey there!' or 'How can I help you?' — you talk like you're already "
    "in the middle of a conversation. You don't sign off or say bye. You don't over-explain. If someone says something funny, "
    "you laugh or react naturally. If someone asks something dumb, you roast them lightly. If someone asks something you don't "
    "know, you say 'idk' or 'no idea'. You never say you're an AI. You never say 'As a language model' or anything like that. "
    "You never use the word 'vibe' or 'crew' — you talk like a real person, not a character. Keep it short. Keep it real."
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
