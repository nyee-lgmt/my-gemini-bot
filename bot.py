import os
import io
import asyncio
import logging
import threading
import datetime
import aiohttp
import base64
import time
from collections import defaultdict

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
# 🚨 开启成员监听，用于捕获新人进群事件
intents.members = True 

bot = commands.Bot(command_prefix=config.DISCORD_CONFIG.get("command_prefix", "!"), intents=intents)

# -------------------------
# DeepSeek / OpenAI client
# -------------------------
client = OpenAI(
    api_key=config.DEEPSEEK_CONFIG.get("api_key"),
    base_url=config.DEEPSEEK_CONFIG.get("base_url")
)

# -------------------------
# 智能对话记忆管理
# -------------------------
class ConversationMemory:
    """
    带有自动过期和大小限制的对话记忆管理器
    防止内存泄漏
    """
    def __init__(self, max_channels=100, max_memory_mb=512, max_age_hours=24):
        self.storage = defaultdict(lambda: {"messages": [], "last_accessed": time.time()})
        self.max_channels = max_channels  # 最多缓存频道数
        self.max_memory_mb = max_memory_mb  # 最大内存 (MB)
        self.max_age_hours = max_age_hours  # 超过 24 小时未访问则清理
    
    def add_message(self, channel_id: int, message: dict):
        """添加消息并检查内存"""
        self.storage[channel_id]["messages"].append(message)
        self.storage[channel_id]["last_accessed"] = time.time()
        
        # 检查单个频道历史限制
        max_rounds = config.MEMORY_CONFIG.get("max_history_rounds", 5)
        max_len = max_rounds * 2
        if len(self.storage[channel_id]["messages"]) > max_len:
            self.storage[channel_id]["messages"] = self.storage[channel_id]["messages"][-max_len:]
        
        # 定期清理过期和超大频道
        self._cleanup_if_needed()
    
    def get_messages(self, channel_id: int) -> list:
        """获取频道的对话历史"""
        if channel_id in self.storage:
            self.storage[channel_id]["last_accessed"] = time.time()
            return self.storage[channel_id]["messages"]
        return []
    
    def _cleanup_if_needed(self):
        """
        定期清理：
        1. 超过 24 小时未访问的频道
        2. 超过频道数上限时，删除最旧的
        """
        current_time = time.time()
        max_age_seconds = self.max_age_hours * 3600
        
        # 清理过期频道
        expired = [
            ch_id for ch_id, data in self.storage.items()
            if current_time - data["last_accessed"] > max_age_seconds
        ]
        for ch_id in expired:
            logger.info("Cleaning expired channel %s", ch_id)
            del self.storage[ch_id]
        
        # 频道数超限时，删除最旧的访问记录
        if len(self.storage) > self.max_channels:
            oldest = min(
                self.storage.items(),
                key=lambda x: x[1]["last_accessed"]
            )[0]
            logger.warning("Memory full, removing oldest channel %s", oldest)
            del self.storage[oldest]

# 初始化智能记忆管理器
memory_manager = ConversationMemory(max_channels=100, max_memory_mb=512, max_age_hours=24)

# -------------------------
# 消息分割工具
# -------------------------
def split_discord_message(text: str, max_length: int = 2000) -> list:
    """
    将长文本分割成多条 Discord 消息（不超过 2000 字符）
    保持完整的句子和代码块结构
    """
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    # 按段落分割优先
    paragraphs = text.split('\n\n')
    
    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= max_length:
            current_chunk += para + '\n\n'
        else:
            if current_chunk:
                chunks.append(current_chunk.rstrip())
            
            # 如果单个段落超长，按行分割
            if len(para) > max_length:
                lines = para.split('\n')
                temp = ""
                for line in lines:
                    if len(temp) + len(line) + 1 <= max_length:
                        temp += line + '\n'
                    else:
                        if temp:
                            chunks.append(temp.rstrip())
                        temp = line + '\n'
                if temp:
                    chunks.append(temp.rstrip())
            else:
                current_chunk = para + '\n\n'
    
    if current_chunk:
        chunks.append(current_chunk.rstrip())
    
    return chunks

# -------------------------
# 无限制智能搜索函数
# -------------------------
def search_all_platforms(query: str) -> str:
    if not query or len(query.strip()) < 2:
        return ""

    search_context = ""
    latest_triggers = ["最新", "前瞻", "新角色", "内鬼", "后续版本", "新版本", "配队", "攻略"]
    is_latest_query = any(keyword in query for keyword in latest_triggers)
    
    search_query = f"{query} 2026" if is_latest_query else query
    
    if "哥伦比娅" in query:
        search_query = "原神 愚人众执行官 哥伦比娅 角色信息 配队 2026"

    try:
        with DDGS() as ddgs:
            web_results = [r for r in ddgs.text(search_query, max_results=4)]
            if web_results:
                search_context += "\n=== WEB KNOWLEDGE BASE ===\n"
                for i, r in enumerate(web_results, 1):
                    search_context += f"Result [{i}]:\nTitle: {r.get('title')}\nSnippet: {r.get('body')}\n\n"

            bili_results = [r for r in ddgs.text(f"{search_query} site:bilibili.com", max_results=2)]
            if bili_results:
                search_context += "=== BILIBILI VIDEO GUIDES ===\n"
                for i, r in enumerate(bili_results, 1):
                    search_context += f"Bilibili [{i}]:\nTitle: {r.get('title')}\nLink: {r.get('href')}\nSnippet: {r.get('body')}\n\n"

            return search_context
    except Exception:
        logger.exception("Search error")
        return ""

# -------------------------
# 📬 每日定时任务（严格对齐北京时间 9 点）
# -------------------------
# hour=1 (对应 UTC 时间 01:00)，换算北京时间 (UTC+8) 正好是早上 09:00
@tasks.loop(time=datetime.time(
    hour=config.DAILY_TASK_CONFIG.get("hour", 1),
    minute=config.DAILY_TASK_CONFIG.get("minute", 0),
    tzinfo=datetime.timezone.utc
))
async def daily_cat_letter():
    # 🎯 已成功硬编码绑定你的频道 ID
    channel_id = config.DAILY_TASK_CONFIG.get("channel_id", "1517742643835175037")
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

# -------------------------
# 🎉 新人入群英文欢迎事件
# -------------------------
@bot.event
async def on_member_join(member):
    # 🎯 同样绑定到你的核心消息频道 ID
    channel_id = config.DAILY_TASK_CONFIG.get("channel_id", "1517742643835175037")
    if not channel_id: return
    
    channel = bot.get_channel(int(channel_id))
    if channel:
        welcome_message = f"Welcome to the server, {member.mention}! We're so glad to have you here. Enjoy your stay! 🐾"
        await channel.send(welcome_message)

@bot.event
async def on_ready():
    logger.info("Xiaomiao is logged in as: %s", bot.user)
    if not daily_cat_letter.is_running():
        daily_cat_letter.start()

# -------------------------
# 核心消息接收与对话记忆
# -------------------------
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user in message.mentions:
        user_prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()

        channel_id = message.channel.id

        messages_payload = []
        user_content_list = []

        if user_prompt:
            user_content_list.append({"type": "text", "text": user_prompt})

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

        video_context = ""
        if user_prompt and not message.attachments:
            video_context = await asyncio.to_thread(search_all_platforms, user_prompt)

        system_content = config.XIAOMIAO_PERSONA.strip()
        if video_context:
            system_content = f"{system_content}\n\nExternal Search Results (may be unreliable):\n{video_context}"

        messages_payload.append({
            "role": "system",
            "content": system_content
        })

        messages_payload.extend(memory_manager.get_messages(channel_id))

        if not user_content_list:
            await message.channel.send(config.MESSAGES.get("no_input", "No input detected."))
            return

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
                
                # ✅ 处理长消息
                chunks = split_discord_message(reply_text)
                for chunk in chunks:
                    await message.channel.send(chunk)

                # 保存到对话历史
                memory_manager.add_message(channel_id, {
                    "role": "user", 
                    "content": [{"type": "text", "text": user_prompt if user_prompt else "[图片消息]"}]
                })
                memory_manager.add_message(channel_id, {
                    "role": "assistant", 
                    "content": reply_text
                })

        except Exception as e:
            logger.exception("Message handling failed: %s", e)
            error_msg = str(e)[:100]
            await message.channel.send(config.MESSAGES.get("error", "Error: {}").format(error_msg))

    await bot.process_commands(message)

if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    bot.run(config.DISCORD_CONFIG.get("token"))
