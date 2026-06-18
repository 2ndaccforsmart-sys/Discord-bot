import re
import time
import logging
import asyncio
import discord
from discord.ext import commands
from collections import defaultdict

from utils.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_HISTORY_LIMIT, GEMINI_BOT_PERSONA, DEFAULT_PERSONA
from utils.security import sanitize_display_name

log = logging.getLogger("bot.ai_chat")

_chat_history: dict[int, list] = defaultdict(list)
_gemini_model = None
_last_bot_response: dict[int, float] = defaultdict(float)

CONTINUATION_WINDOW = 120

RELEVANCE_KEYWORDS = [
    "server", "minecraft", "aternos", "online", "offline", "start", "stop",
    "ip", "join", "player", "lag", "crash", "port", "whitelist", "op",
    "realm", "mod", "plugin", "seed", "world", "backup", "restart",
]

BOT_NAME_ALIASES = ["server_start", "server start", "start", "bot", "botty"]


def init_gemini() -> bool:
    global _gemini_model
    if not GEMINI_API_KEY:
        log.warning("No GEMINI_API_KEY set, AI chat disabled.")
        return False
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        generation_config = {
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 30,
            "max_output_tokens": 256,
        }
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        _gemini_model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            generation_config=generation_config,
            safety_settings=safety_settings,
            system_instruction=GEMINI_BOT_PERSONA or DEFAULT_PERSONA,
        )
        log.info("Gemini AI initialized: %s", GEMINI_MODEL)
        return True
    except Exception as e:
        log.error("Failed to initialize Gemini: %s", e)
        _gemini_model = None
        return False


async def ask_gemini(channel_id: int, user_message: str, author_name: str) -> str | None:
    if not _gemini_model:
        return None

    sanitized_name = sanitize_display_name(author_name)
    history = _chat_history[channel_id]
    history.append({"role": "user", "parts": [f"[{sanitized_name}]: {user_message}"]})

    if len(history) > GEMINI_HISTORY_LIMIT:
        _chat_history[channel_id] = history[-GEMINI_HISTORY_LIMIT:]
        history = _chat_history[channel_id]

    try:
        loop = asyncio.get_running_loop()

        def call_gemini():
            chat = _gemini_model.start_chat(history=history)
            response = chat.send_message(user_message)
            return response.text

        response_text = await loop.run_in_executor(None, call_gemini)
        history.append({"role": "model", "parts": [response_text]})

        if len(history) > GEMINI_HISTORY_LIMIT:
            _chat_history[channel_id] = history[-GEMINI_HISTORY_LIMIT:]

        if len(response_text) > 1900:
            response_text = response_text[:1900] + "..."
        return response_text
    except Exception as e:
        log.error("Gemini error: %s", e)
        if history and history[-1]["role"] == "user":
            history.pop()
        return None


def mark_bot_responded(channel_id: int):
    _last_bot_response[channel_id] = time.time()


def _is_mentioning_bot(content: str, bot_user: discord.Member) -> bool:
    content_lower = content.lower()
    bot_name = bot_user.display_name.lower().replace(" ", "")
    if bot_name and bot_name in content_lower.replace(" ", ""):
        return True
    for alias in BOT_NAME_ALIASES:
        if alias in content_lower:
            return True
    return False


def _looks_like_continuation(content: str) -> bool:
    if len(content) > 200:
        return False
    if content.startswith("!"):
        return False
    return True


def should_bot_respond(message: discord.Message, bot_user: discord.Member) -> bool:
    content = message.content
    if not content:
        return False
    content_stripped = content.lower().strip()
    if not content_stripped:
        return False

    if message.reference and message.reference.resolved:
        replied = message.reference.resolved
        if hasattr(replied, 'author') and replied.author == bot_user:
            return True

    if _is_mentioning_bot(content, bot_user):
        return True

    if re.search(r'\b(bot|botty)\b', content_stripped) and content_stripped.endswith("?"):
        return True

    if any(kw in content_stripped for kw in RELEVANCE_KEYWORDS) and "?" in content_stripped:
        return True

    channel_id = message.channel.id
    last_response = _last_bot_response.get(channel_id, 0)
    time_since = time.time() - last_response
    if time_since < CONTINUATION_WINDOW and _looks_like_continuation(content):
        return True

    return False


class AIChat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.content:
            return
        if not GEMINI_API_KEY or not _gemini_model:
            return
        if not should_bot_respond(message, self.bot.user):
            return

        clean_content = message.content
        if self.bot.user in message.mentions:
            clean_content = re.sub(r'<@!?\d+>', '', message.content).strip()

        if clean_content:
            async with message.channel.typing():
                response = await ask_gemini(message.channel.id, clean_content, message.author.display_name)
            if response:
                mark_bot_responded(message.channel.id)
                await message.reply(response, mention_author=False)

    @commands.command(name="chat")
    async def chat_command(self, ctx: commands.Context, *, message: str = ""):
        if not GEMINI_API_KEY or not _gemini_model:
            await ctx.send("AI not configured. Set `GEMINI_API_KEY` in .env.")
            return
        if not message:
            await ctx.send("Usage: `!chat <your message>`")
            return
        async with ctx.typing():
            response = await ask_gemini(ctx.channel.id, message, ctx.author.display_name)
        if response:
            mark_bot_responded(ctx.channel.id)
            await ctx.send(response)
        else:
            await ctx.send("Failed to respond. Try again.")

    @commands.command(name="bot")
    async def botchat_alias(self, ctx: commands.Context, *, message: str = ""):
        await self.chat_command(ctx, message=message)

    @commands.command(name="clear")
    async def clear_command(self, ctx: commands.Context):
        if ctx.channel.id in _chat_history:
            _chat_history[ctx.channel.id].clear()
        await ctx.send("Conversation history cleared.")


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChat(bot))
