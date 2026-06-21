import os
import io
import asyncio
import logging
import threading
import datetime
import aiohttp
import base64
import time
import random  # 引入随机数用于闲聊抖动
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
# 🧠 健壮的指数退避 API 重试代理 (整合超时机制)
# -------------------------
async def call_deepseek_with_retry(messages, max_retries=3):
    """
    带指数退避和 30 秒超时控制的大模型请求包装器
    """
    for attempt in range(max_retries):
        try:
            return await asyncio.to_thread(
                client.chat.completions.create,
                model=config.DEEPSEEK_CONFIG.get("model"),
                messages=messages,
                stream=False,
                timeout=30  # 添加 30 秒强超时限制
            )
        except asyncio.TimeoutError:
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s 指数退避
            else:
                raise
        except Exception as e:
            logger.error(f"API Attempt {attempt+1} failed: {type(e).__name__}: {e}")
            if attempt == max_retries - 1:
                raise

# -------------------------
# 智能对话记忆管理
# -------------------------
class ConversationMemory:
    """
    带有自动过期和大小限制的对话记忆管理器
    """
    def __init__(self, max_channels=100, max_memory_mb=512, max_age_hours=24):
        self.storage = defaultdict(lambda: {"messages": [], "last_accessed": time.time()})
        self.max_channels = max_channels
        self.max_memory_mb = max_memory_mb
        self.max_age_hours = max_age_hours

    def add_message(self, channel_id: int, message: dict):
        self.storage[channel_id]["messages"].append(message)
        self.storage[channel_id]["last_accessed"] = time.time()

        max_rounds = config.MEMORY_CONFIG.get("max_history_rounds", 5)
        max_len = max_rounds * 2
        if len(self.storage[channel_id]["messages"]) > max_len:
            self.storage[channel_id]["messages"] = self.storage[channel_id]["messages"][-max_len:]

        self._cleanup_if_needed()

    def get_messages(self, channel_id: int) -> list:
        if channel_id in self.storage:
            self.storage[channel_id]["last_accessed"] = time.time()
            return self.storage[channel_id]["messages"]
        return []

    def _cleanup_if_needed(self):
        current_time = time.time()
        max_age_seconds = self.max_age_hours * 3600

        expired = [
            ch_id for ch_id, data in self.storage.items()
            if current_time - data["last_accessed"] > max_age_seconds
        ]
        for ch_id in expired:
            logger.info("Cleaning expired channel %s", ch_id)
            del self.storage[ch_id]

        if len(self.storage) > self.max_channels:
            oldest = min(self.storage.items(), key=lambda x: x[1]["last_accessed"])[0]
            logger.warning("Memory full, removing oldest channel %s", oldest)
            del self.storage[oldest]

memory_manager = ConversationMemory(max_channels=100, max_memory_mb=512, max_age_hours=24)

# -------------------------
# 消息分割工具
# -------------------------
def split_discord_message(text: str, max_length: int = 2000) -> list:
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""
    paragraphs = text.split('\n\n')

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= max_length:
            current_chunk += para + '\n\n'
        else:
            if current_chunk:
                chunks.append(current_chunk.rstrip())

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
            return search_context
    except Exception:
        logger.exception("Search error")
        return ""

# -------------------------
# 📬 每日定时任务（严格对齐北京时间 9 点）
# -------------------------
@tasks.loop(time=datetime.time(
    hour=config.DAILY_TASK_CONFIG.get("hour", 1),
    minute=config.DAILY_TASK_CONFIG.get("minute", 0),
    tzinfo=datetime.timezone.utc
))
async def daily_cat_letter():
    channel_id = config.DAILY_TASK_CONFIG.get("channel_id", "1517742643835175037")
    if not channel_id: return

    channel = bot.get_channel(int(channel_id))
    if not channel: return

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    prompt = config.DAILY_LETTER_PROMPT.format(date=today_str)
    try:
        # 🎯 改用优化后的重试包装代理
        response = await call_deepseek_with_retry([{"role": "user", "content": prompt}])
        reply_text = response.choices[0].message.content if hasattr(response, "choices") else str(response)
        await channel.send(f"{config.MESSAGES.get('daily_letter_header','')}{reply_text}\n━━━━━━━━━━━━━━━━━━━━")
    except Exception as e:
        logger.exception("Daily letter failed: %s", e)

# -------------------------
# 💬 每日每隔 X 小时自动“主动闲聊”任务
# -------------------------
@tasks.loop(hours=4.0)  # 每隔 4 小时主动在群里冒泡一次，数字可自己改
async def random_chat_task():
    channel_id = config.DAILY_TASK_CONFIG.get("channel_id", "1517742643835175037")
    if not channel_id: return

    channel = bot.get_channel(int(channel_id))
    if not channel: return

    system_content = config.XIAOMIAO_PERSONA.strip()
    chat_prompt = (
        "你现在要主动在服务器群聊里发一条简短的信息打个招呼。 "
        "请结合你傲娇、可爱的猫娘小喵人设，随机选择一个主题（比如：抱怨天气、伸懒腰、提醒主人喝水、分享刚抓到蝴蝶的喜悦，或是问大家在干嘛）。"
        "字数严格控制在 40 字以内，带上猫爪 🐾 等符合身份的颜表情，语气要生动活泼喵！"
    )

    try:
        # 🎯 利用重试包装代理请求
        response = await call_deepseek_with_retry([
            {"role": "system", "content": system_content},
            {"role": "user", "content": chat_prompt}
        ])
        chat_msg = response.choices[0].message.content if hasattr(response, "choices") else ""
        if chat_msg.strip():
            await channel.send(chat_msg.strip())
    except Exception as e:
        logger.error("Failed to execute random chat push: %s", e)

# -------------------------
# 🎉 新人入群智能 AI 欢迎事件
# -------------------------
@bot.event
async def on_member_join(member):
    logger.info("Detect new member joined: %s", member.name)
    
    raw_channel_id = config.DAILY_TASK_CONFIG.get("channel_id", "1517742643835175037")
    if not raw_channel_id: return

    channel = bot.get_channel(int(raw_channel_id))
    if channel:
        system_content = config.XIAOMIAO_PERSONA.strip()
        welcome_prompt = (
            f"群里新加入了一位成员，他的名字叫 '{member.name}'。 "
            f"请用你专属的温暖、俏皮的猫娘口吻（带一些有意思的爪印或颜表情），写一句1到2句的简短群聊欢迎语，"
            f"并贴心地提醒他，如果想找你聊天，可以随时在频道里 @Xiaomiao 呼唤你喵~"
        )
        
        try:
            # 🎯 同样采用重试包装代理
            response = await call_deepseek_with_retry([
                {"role": "system", "content": system_content},
                {"role": "user", "content": welcome_prompt}
            ])
            ai_welcome_msg = response.choices[0].message.content if hasattr(response, "choices") else ""
            
            if ai_welcome_msg.strip():
                await channel.send(f"{member.mention} {ai_welcome_msg.strip()}")
                return
        except Exception as e:
            logger.error("AI failed to generate welcome message: %s", e)
            
        fallback_msg = f"Welcome to the server, {member.mention}! (🐾•̀ω•́)🐾 呜喵~ 欢迎新朋友刚刚降落！我是小喵，有什么问题或者想聊天都可以随时 @我 呼唤我哦喵~"
        await channel.send(fallback_msg)

@bot.event
async def on_ready():
    logger.info("Xiaomiao is logged in as: %s", bot.user)
    # 启动 9点 定时任务
    if not daily_cat_letter.is_running():
        daily_cat_letter.start()
    # 启动 主动闲聊 定时任务
    if not random_chat_task.is_running():
        random_chat_task.start()

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
                # 🎯 全面换用重试控制逻辑
                response = await call_deepseek_with_retry(messages_payload)

                reply_text = response.choices[0].message.content if hasattr(response, "choices") else str(response)

                chunks = split_discord_message(reply_text)
                for chunk in chunks:
                    await message.channel.send(chunk)

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
