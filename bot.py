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

# 🧠 全局持久化记忆库
conversation_history = {}

# -------------------------
# 🧠 强力修正版智能搜索函数（禁止瞎猜，遇到游戏核心词强制联网）
# -------------------------
def search_all_platforms(query: str) -> str:
    # 🚨 核心防御：只要用户提到这些关键词，不管有没有带“搜/查”，一律强制开启联网搜索！
    GAME_TRIGGERS = ["原神", "配队", "攻略", "角色", "哥伦比娅", "少女"]
    is_game_query = any(trigger in query for trigger in GAME_TRIGGERS)
    
    # 既没有触发游戏词，也没有触发常规配置关键词，才不联网
    if not (is_game_query or any(kw in query for kw in config.SEARCH_CONFIG.get("keywords", []))):
        return ""

    search_context = ""
    
    # 时效性动态触发
    latest_triggers = config.SEARCH_CONFIG.get("latest_keywords", []) + ["最新", "前瞻", "新角色", "内鬼", "后续版本", "新版本"]
    is_latest_query = any(keyword in query for keyword in latest_triggers)
    
    search_query = f"{query} 2026" if is_latest_query else query
    
    # 🎯 针对“哥伦比娅”的精准纠偏：如果包含此名字，直接优化搜索词，不给搜索引擎任何装糊涂的机会
    if "哥伦比娅" in query:
        search_query = "原神 愚人众执行官 哥伦比娅 角色信息 配队 2026"

    try:
        with DDGS() as ddgs:
            # 1. 全网综合文本搜索
            web_results = [r for r in ddgs.text(search_query, max_results=4)]
            if web_results:
                search_context += "\n=== WEB KNOWLEDGE BASE ===\n"
                for i, r in enumerate(web_results, 1):
                    search_context += f"Result [{i}]:\nTitle: {r.get('title')}\nSnippet: {r.get('body')}\n\n"

            # 2. Bilibili 视频辅助小抄
            bili_results = [r for r in ddgs.text(f"{search_query} site:bilibili.com", max_results=config.SEARCH_CONFIG.get("bilibili_max_results", 2))]
            if bili_results:
                search_context += "=== BILIBILI VIDEO GUIDES ===\n"
                for i, r in enumerate(bili_results, 1):
                    search_context += f"Bilibili [{i}]:\nTitle: {r.get('title')}\nLink: {r.get('href')}\nSnippet: {r.get('body')}\n\n"

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
    if not channel_id: return

    channel = bot.get_channel(int(channel_id))
    if not channel: return

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    prompt = config.DAILY_LETTER_PROMPT.format(date=today_str)
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=config.DEEPSEEK_CONFIG.get("model"),
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        reply_text = response.choices[0].message.content if hasattr(response, "choices") else str(response)
        await channel.send(f"{config.MESSAGES.get('daily_letter_header','')}{reply_text}\n━━━━━━━━━━━━━━━━━━━━")
    except Exception as e:
        logger.exception("Daily letter failed: %s", e)

@bot.event
async def on_ready():
    logger.info("Xiaomiao is logged in as: %s", bot.user)
    if not daily_cat_letter.is_running():
        daily_cat_letter.start()

# -------------------------
# 核心消息接收与记忆对齐
# -------------------------
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user in message.mentions:
        user_prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()

        channel_id = message.channel.id
        if channel_id not in conversation_history:
            conversation_history[channel_id] = []

        messages_payload = []
        user_content_list = []

        if user_prompt:
            user_content_list.append({"type": "text", "text": user_prompt})

        # 图片附件无损转 Base64 塞入当前 Payload
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
                                    base64_image = base64.b64encode(image_data).decode('utf-8')
                                    user_content_list.append({
                                        "type": "image_url",
                                        "image_url": {"url": f"data:{attachment.content_type};base64,{base64_image}"}
                                    })
                                else:
                                    logger.warning("Failed to download attachment %s", attachment.url)
                    except Exception:
                        logger.exception("Image handling error")

        # 触发智能弹性搜索（已经整合了强制游戏检索）
        video_context = ""
        if user_prompt and not message.attachments:
            video_context = await asyncio.to_thread(search_all_platforms, user_prompt)

        # 1. 注入人设与联网搜索结果
        system_content = config.XIAOMIAO_PERSONA.strip()
        if video_context:
            system_content = f"{system_content}\n\nExternal Search Results (may be unreliable):\n{video_context}"

        messages_payload.append({
            "role": "system",
            "content": system_content
        })

        # 2. 追加历史轮次记忆（格式完全规范统一）
        messages_payload.extend(conversation_history[channel_id])

        if not user_content_list:
            await message.channel.send(config.MESSAGES.get("no_input", "No input detected."))
            return

        # 3. 拼接用户当前这一轮的输入
        messages_payload.append({"role": "user", "content": user_content_list})

        try:
            async with message.channel.typing():
                response = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=config.DEEPSEEK_CONFIG.get("model"),
                    messages=messages_payload,
                    stream=False
                )

                reply_text = response.choices[0].message.content if hasattr(response, "choices") else str(response)
                await message.channel.send(reply_text)

                # 4. 记忆库中统一采用结构化字典保存，杜绝选择性失忆
                conversation_history[channel_id].append({
                    "role": "user", 
                    "content": [{"type": "text", "text": user_prompt if user_prompt else "[图片消息]"}]
                })
                conversation_history[channel_id].append({
                    "role": "assistant", 
                    "content": reply_text
                })

                # 严格裁剪记忆轮数
                max_rounds = config.MEMORY_CONFIG.get("max_history_rounds", 5)
                max_len = max_rounds * 2
                conversation_history[channel_id] = conversation_history[channel_id][-max_len:]

        except Exception as e:
            logger.exception("Message handling failed: %s", e)
            await message.channel.send(config.MESSAGES.get("error", "Error: {}").format(e))

    await bot.process_commands(message)

if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    bot.run(config.DISCORD_CONFIG.get("token"))
