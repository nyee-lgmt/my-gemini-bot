import os
import io
import asyncio
import logging
import threading
import datetime
import aiohttp
import base64

import discord
from discord.ext import tasks, commands
from openai import OpenAI
from flask import Flask
from duckduckgo_search import DDGS

import config

# -------------------------
# Basic logging
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("my-gemini-bot")

# -------------------------
# Validate required envs
# -------------------------
try:
    config.validate_required_envs()
except Exception as e:
    logger.error("Configuration validation failed: %s", e)
    raise SystemExit(f"Configuration validation failed: {e}")

# -------------------------
# Flask Web server (light)
# -------------------------
app = Flask("my-gemini-bot")


@app.route("/")
def home():
    return config.MESSAGES.get("web_home", "Bot is running.")


def run_web_server():
    host = config.FLASK_CONFIG.get("host", "0.0.0.0")
    port = int(config.FLASK_CONFIG.get("port", 8080))
    # Note: For production, run a proper WSGI/ASGI server instead of Flask dev server.
    app.run(host=host, port=port)


# -------------------------
# Discord bot setup
# -------------------------
intents = discord.Intents.default()
intents.message_content = bool(config.DISCORD_CONFIG.get("message_content", True))
bot = commands.Bot(command_prefix=config.DISCORD_CONFIG.get("command_prefix", "!"), intents=intents)

# -------------------------
# DeepSeek / OpenAI client
# -------------------------
client = OpenAI(
    api_key=config.DEEPSEEK_CONFIG.get("api_key"),
    base_url=config.DEEPSEEK_CONFIG.get("base_url")
)

# -------------------------
# In-memory conversation history
# Use a simple dict; consider persisting or using LRU cache for many channels.
# -------------------------
conversation_history = {}

# -------------------------
# Helper: upload image bytes to anonymous file host (0x0.st)
# Returns URL string or None on failure.
# -------------------------
async def upload_image_bytes(image_bytes: bytes, filename: str) -> str | None:
    upload_url = "https://0x0.st"
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            data = aiohttp.FormData()
            data.add_field("file", image_bytes, filename=filename, content_type="application/octet-stream")
            async with session.post(upload_url, data=data) as resp:
                if resp.status == 200:
                    text = (await resp.text()).strip()
                    # 0x0.st returns plain URL on success
                    return text
                else:
                    logger.warning("Upload failed to %s: status=%s", upload_url, resp.status)
    except Exception:
        logger.exception("Exception during image upload")
    return None


# -------------------------
# Blocking search helper (kept sync) — will be executed in thread to avoid blocking event loop
# -------------------------
def search_all_platforms(query: str) -> str:
    SEARCH_KEYWORDS = config.SEARCH_CONFIG.get("keywords", [])
    if not any(kw in query for kw in SEARCH_KEYWORDS):
        return ""

    search_context = ""
    is_latest_query = any(keyword in query for keyword in config.SEARCH_CONFIG.get("latest_keywords", []))
    search_query = f"{query} 2026" if is_latest_query else query

    try:
        with DDGS() as ddgs:
            # Bilibili
            bili_results = [r for r in ddgs.text(f"{search_query} site:bilibili.com", max_results=config.SEARCH_CONFIG.get("bilibili_max_results", 2))]
            if bili_results:
                search_context += "\n=== BILIBILI VIDEO GUIDES ===\n"
                for i, r in enumerate(bili_results, 1):
                    search_context += f"Bilibili [{i}]:\nTitle: {r.get('title')}\nLink: {r.get('href')}\nSnippet: {r.get('body')}\n\n"

            # YouTube
            yt_results = [r for r in ddgs.text(f"{search_query} site:youtube.com", max_results=config.SEARCH_CONFIG.get("youtube_max_results", 2))]
            if yt_results:
                search_context += "=== YOUTUBE VIDEO GUIDES ===\n"
                for i, r in enumerate(yt_results, 1):
                    search_context += f"YouTube [{i}]:\nTitle: {r.get('title')}\nLink: {r.get('href')}\nSnippet: {r.get('body')}\n\n"

            if not search_context:
                return config.MESSAGES.get("search_notice", "").format(query)
            return search_context
    except Exception:
        logger.exception("Search error")
        return ""


# -------------------------
# Daily task
# -------------------------
@tasks.loop(time=datetime.time(
    hour=config.DAILY_TASK_CONFIG.get("hour", 1),
    minute=config.DAILY_TASK_CONFIG.get("minute", 0),
    tzinfo=datetime.timezone.utc
))
async def daily_cat_letter():
    channel_id = config.DAILY_TASK_CONFIG.get("channel_id")
    if not channel_id:
        logger.warning("DAILY_TASK_CONFIG.channel_id not set; skipping daily_cat_letter")
        return

    channel = bot.get_channel(int(channel_id))
    if not channel:
        logger.warning("Daily letter channel not found: %s", channel_id)
        return

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    prompt = config.DAILY_LETTER_PROMPT.format(date=today_str)
    try:
        # Run LLM call in thread to avoid blocking
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=config.DEEPSEEK_CONFIG.get("model"),
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        # Attempt to read content robustly
        reply_text = ""
        if hasattr(response, "choices") and response.choices:
            try:
                reply_text = response.choices[0].message.content
            except Exception:
                reply_text = str(response.choices[0])
        else:
            reply_text = str(response)
        await channel.send(f"{config.MESSAGES.get('daily_letter_header','')}{reply_text}\n━━━━━━━━━━━━━━━━━━━━")
    except Exception as e:
        logger.exception("Daily letter failed: %s", e)


# -------------------------
# Bot events and message handling
# -------------------------
@bot.event
async def on_ready():
    logger.info("Xiaomiao is logged in as: %s", bot.user)
    if not daily_cat_letter.is_running():
        daily_cat_letter.start()


@bot.event
async def on_message(message):
    # Ignore messages from self
    if message.author == bot.user:
        return

    # Only respond when bot is mentioned
    if bot.user in message.mentions:
        # Extract user prompt text (remove mention)
        user_prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()

        channel_id = message.channel.id
        if channel_id not in conversation_history:
            conversation_history[channel_id] = []

        messages_payload = []
        user_content_items = []

        if user_prompt:
            user_content_items.append({"type": "text", "text": user_prompt})

        # Handle attachments: upload and include URL in user content
        if message.attachments:
            for attachment in message.attachments:
                fname = attachment.filename or "image"
                if any(fname.lower().endswith(ext) for ext in config.IMAGE_CONFIG.get("extensions", [])):
                    await message.channel.send(config.MESSAGES.get("image_loading", "Processing image..."))
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(attachment.url) as resp:
                                if resp.status == 200:
                                    image_data = await resp.read()
                                    # Try to upload image to anonymous host
                                    uploaded_url = await upload_image_bytes(image_data, fname)
                                    if uploaded_url:
                                        user_content_items.append({"type": "image_url", "text": uploaded_url})
                                    else:
                                        # Fallback: include a small base64 thumbnail note (avoid sending whole image)
                                        try:
                                            # produce very small thumbnail-like base64 (not a real thumbnail)
                                            b64_preview = base64.b64encode(image_data[:1024]).decode("utf-8")
                                            user_content_items.append({"type": "image_url", "text": f"[base64-preview:{b64_preview}]"})
                                        except Exception:
                                            user_content_items.append({"type": "image_url", "text": "[IMAGE]"})
                                else:
                                    logger.warning("Failed to download attachment %s: status %s", attachment.url, resp.status)
                    except Exception:
                        logger.exception("Image handling error for %s", attachment.url)

        # Trigger web search if needed (run in thread to avoid blocking)
        video_context = ""
        if user_prompt and not message.attachments:
            video_context = await asyncio.to_thread(search_all_platforms, user_prompt)

        # Assemble system prompt (persona + search context)
        system_content = config.XIAOMIAO_PERSONA.strip()
        if video_context:
            system_content = f"{system_content}\n\nExternal Search Results (may be unreliable):\n{video_context}"

        messages_payload.append({
            "role": "system",
            "content": system_content
        })

        # Attach recent conversation history
        messages_payload.extend(conversation_history[channel_id])

        if not user_content_items:
            await message.channel.send(config.MESSAGES.get("no_input", "No input detected."))
            return

        # Convert user_content_items list into a single string for LLM
        content_parts = []
        for item in user_content_items:
            if item.get("type") == "text":
                content_parts.append(item.get("text", ""))
            elif item.get("type") == "image_url":
                content_parts.append(f"[IMAGE_URL] {item.get('text')}")
        user_content_str = "\n".join([p for p in content_parts if p]).strip()
        messages_payload.append({"role": "user", "content": user_content_str})

        try:
            async with message.channel.typing():
                # Call LLM in thread to avoid blocking event loop
                response = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=config.DEEPSEEK_CONFIG.get("model"),
                    messages=messages_payload,
                    stream=False
                )

                # Extract reply text robustly
                reply_text = ""
                if hasattr(response, "choices") and response.choices:
                    try:
                        reply_text = response.choices[0].message.content
                    except Exception:
                        try:
                            # Some SDKs use different structure
                            reply_text = response.choices[0].text
                        except Exception:
                            reply_text = str(response.choices[0])
                else:
                    reply_text = str(response)

                # Send reply
                await message.channel.send(reply_text)

                # Update memory: store user's prompt (as text) and assistant reply
                conversation_history[channel_id].append({"role": "user", "content": user_content_str})
                conversation_history[channel_id].append({"role": "assistant", "content": reply_text})

                # Trim memory according to config
                max_rounds = config.MEMORY_CONFIG.get("max_history_rounds", 5)
                max_len = max_rounds * 2
                conversation_history[channel_id] = conversation_history[channel_id][-max_len:]

        except Exception as e:
            logger.exception("Message handling failed: %s", e)
            try:
                await message.channel.send(config.MESSAGES.get("error", "Error: {}").format(e))
            except Exception:
                logger.exception("Failed to send error message to channel")

    # allow commands to be processed as well
    await bot.process_commands(message)


# -------------------------
# Start web server and bot
# -------------------------
if __name__ == "__main__":
    # For local dev: start web server thread and bot
    threading.Thread(target=run_web_server, daemon=True).start()
    bot.run(config.DISCORD_CONFIG.get("token"))
