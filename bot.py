import os
import io
import asyncio
import logging
import threading
import datetime
import aiohttp
import base64
import time
import random
import signal
import sys
from collections import defaultdict
from typing import List, Dict, Optional

import discord
from discord.ext import tasks, commands
from openai import OpenAI
from flask import Flask
from duckduckgo_search import DDGS

import config

# -------------------------
# Basic logging
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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

@app.route("/health")
def health():
    return {"status": "ok", "timestamp": datetime.datetime.now().isoformat()}

def run_web_server() -> None:
    """运行 Flask 服务器的包装函数"""
    try:
        host = config.FLASK_CONFIG.get("host", "0.0.0.0")
        port = int(config.FLASK_CONFIG.get("port", 8080))
        logger.info("Starting Flask server on %s:%d", host, port)
        app.run(host=host, port=port, debug=False, use_reloader=False)
    except Exception as e:
        logger.error("Flask server crashed: %s", e, exc_info=True)
        sys.exit(1)

# -------------------------
# Discord bot setup
# -------------------------
intents = discord.Intents.default()
intents.message_content = bool(config.DISCORD_CONFIG.get("message_content", True))
intents.members = True  # 监听成员事件

bot = commands.Bot(command_prefix=config.DISCORD_CONFIG.get("command_prefix", "!"), intents=intents)

# -------------------------
# DeepSeek / OpenAI client
# -------------------------
client = OpenAI(
    api_key=config.DEEPSEEK_CONFIG.get("api_key"),
    base_url=config.DEEPSEEK_CONFIG.get("base_url")
)

# -------------------------
# 🧠 智能 API 重试代理（改进版）
# -------------------------
RETRYABLE_ERRORS = (
    asyncio.TimeoutError,
    ConnectionError,
    TimeoutError,
)

async def call_deepseek_with_retry(
    messages: List[Dict], 
    max_retries: int = 3
) -> Optional[object]:
    """
    带指数退避和 30 秒超时控制的大模型请求包装器（改进版）
    
    Args:
        messages: 对话消息列表
        max_retries: 最大重试次数
        
    Returns:
        API 响应对象，或 None（失败时）
        
    Raises:
        Exception: 不可重试的错误
    """
    for attempt in range(max_retries):
        try:
            logger.debug(f"API call attempt {attempt + 1}/{max_retries}")
            return await asyncio.to_thread(
                client.chat.completions.create,
                model=config.DEEPSEEK_CONFIG.get("model"),
                messages=messages,
                stream=False,
                timeout=30
            )
        except RETRYABLE_ERRORS as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(
                    "API call failed (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1, max_retries, wait_time, type(e).__name__
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(
                    "API call failed after %d attempts: %s",
                    max_retries, type(e).__name__, exc_info=True
                )
                raise
        except Exception as e:
            # 非重试错误直接抛出
            logger.error(
                "Non-retryable API error: %s: %s",
                type(e).__name__, e, exc_info=True
            )
            raise

# -------------------------
# 智能对话记忆管理（并发安全 + 内存管理）
# -------------------------
class ConversationMemory:
    """
    带有自动过期、大小限制和并发安全的对话记忆管理器
    """
    def __init__(self, max_channels: int = 100, max_memory_mb: float = 512, max_age_hours: int = 24):
        self.storage: Dict = defaultdict(lambda: {"messages": [], "last_accessed": time.time()})
        self.max_channels = max_channels
        self.max_memory_mb = max_memory_mb
        self.max_age_hours = max_age_hours
        self.memory_size = 0.0  # 实时追踪内存使用（单位 MB）
        self.lock = asyncio.Lock()  # 🔒 并发安全锁
        logger.info("ConversationMemory initialized (max_channels=%d, max_memory_mb=%.1f)", 
                   max_channels, max_memory_mb)

    @staticmethod
    def _estimate_size(obj: object) -> float:
        """估算对象内存占用（单位 MB）"""
        import sys
        return sys.getsizeof(str(obj)) / (1024 * 1024)

    async def add_message(self, channel_id: int, message: Dict) -> None:
        """添加消息到指定频道的记忆中（线程安全）"""
        async with self.lock:
            msg_size = self._estimate_size(message)
            self.storage[channel_id]["messages"].append(message)
            self.storage[channel_id]["last_accessed"] = time.time()
            self.memory_size += msg_size

            # 限制单个频道的历史轮数
            max_rounds = config.MEMORY_CONFIG.get("max_history_rounds", 5)
            max_len = max_rounds * 2
            if len(self.storage[channel_id]["messages"]) > max_len:
                old_messages = self.storage[channel_id]["messages"][:-max_len]
                self.memory_size -= sum(self._estimate_size(m) for m in old_messages)
                self.storage[channel_id]["messages"] = self.storage[channel_id]["messages"][-max_len:]

            await self._cleanup_if_needed()

    async def get_messages(self, channel_id: int) -> List[Dict]:
        """获取指定频道的消息历史（线程安全）"""
        async with self.lock:
            if channel_id in self.storage:
                self.storage[channel_id]["last_accessed"] = time.time()
                return self.storage[channel_id]["messages"].copy()
            return []

    async def _cleanup_if_needed(self) -> None:
        """根据条件清理过期或超量的频道数据（需在持有锁的情况下调用）"""
        current_time = time.time()
        max_age_seconds = self.max_age_hours * 3600

        # 第一步：清理过期频道
        expired = [
            ch_id for ch_id, data in self.storage.items()
            if current_time - data["last_accessed"] > max_age_seconds
        ]
        for ch_id in expired:
            logger.info("Cleaning expired channel %d", ch_id)
            self.memory_size -= sum(self._estimate_size(m) 
                                   for m in self.storage[ch_id]["messages"])
            del self.storage[ch_id]

        # 第二步：如果超过频道数量限制，清理最少使用的频道
        if len(self.storage) > self.max_channels:
            oldest = min(self.storage.items(), key=lambda x: x[1]["last_accessed"])[0]
            logger.warning(
                "Memory full (channels=%d), removing oldest channel %d",
                len(self.storage), oldest
            )
            self.memory_size -= sum(self._estimate_size(m) 
                                   for m in self.storage[oldest]["messages"])
            del self.storage[oldest]

        # 第三步：如果内存超限，按 LRU 策略清理
        while self.memory_size > self.max_memory_mb and self.storage:
            oldest = min(self.storage.items(), key=lambda x: x[1]["last_accessed"])[0]
            logger.warning(
                "Memory exceeded (%.2f MB > %.2f MB), removing channel %d",
                self.memory_size, self.max_memory_mb, oldest
            )
            self.memory_size -= sum(self._estimate_size(m) 
                                   for m in self.storage[oldest]["messages"])
            del self.storage[oldest]

memory_manager = ConversationMemory(
    max_channels=100,
    max_memory_mb=512,
    max_age_hours=24
)

# -------------------------
# 消息分割工具
# -------------------------
def split_discord_message(text: str, max_length: int = 2000) -> List[str]:
    """
    将长文本分割为多个 Discord 消息（单条最多 2000 字符）
    
    Args:
        text: 待分割文本
        max_length: 单条消息最大长度
        
    Returns:
        分割后的消息列表
    """
    if len(text) <= max_length:
        return [text]

    chunks: List[str] = []
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
# 无限制智能搜索函数（改进异常处理）
# -------------------------
def search_all_platforms(query: str) -> str:
    """
    使用 DuckDuckGo 搜索信息并返回格式化结果
    
    Args:
        query: 搜索关键词
        
    Returns:
        格式化的搜索结果字符串，失败时返回空字符串
    """
    if not query or len(query.strip()) < 2:
        logger.debug("Search query too short or empty")
        return ""

    search_context = ""
    latest_triggers = ["最新", "前瞻", "新角色", "内鬼", "后续版本", "新版本", "配队", "攻略"]
    is_latest_query = any(keyword in query for keyword in latest_triggers)

    search_query = f"{query} 2026" if is_latest_query else query

    if "哥伦比娅" in query:
        search_query = "原神 愚人众执行官 哥伦比娅 角色信息 配队 2026"

    try:
        with DDGS() as ddgs:
            try:
                logger.debug("Searching for: %s", search_query)
                web_results = list(ddgs.text(search_query, max_results=4))
                
                if web_results:
                    search_context += "\n=== WEB KNOWLEDGE BASE ===\n"
                    for i, r in enumerate(web_results, 1):
                        title = r.get('title', 'N/A')
                        body = r.get('body', 'N/A')
                        search_context += f"Result [{i}]:\nTitle: {title}\nSnippet: {body}\n\n"
                    logger.debug("Search returned %d results", len(web_results))
                else:
                    logger.warning("Search returned no results for query: %s", search_query)
                
                return search_context
                
            except TimeoutError as e:
                logger.warning("Search timeout for query '%s': %s", query, str(e))
                return ""
            except Exception as e:
                logger.error(
                    "Search failed for query '%s': %s",
                    query, type(e).__name__, exc_info=True
                )
                return ""
                
    except Exception as e:
        logger.error(
            "Unexpected error in search_all_platforms: %s",
            str(e), exc_info=True
        )
        return ""

# -------------------------
# 📬 每日定时任务（北京时间 9 点）
# -------------------------
@tasks.loop(time=datetime.time(
    hour=config.DAILY_TASK_CONFIG.get("hour", 1),
    minute=config.DAILY_TASK_CONFIG.get("minute", 0),
    tzinfo=datetime.timezone.utc
))
async def daily_cat_letter() -> None:
    """发送每日信件的定时任务"""
    channel_id = config.DAILY_TASK_CONFIG.get("channel_id", "1517742643835175037")
    if not channel_id:
        logger.warning("Daily task: channel_id not configured")
        return

    channel = bot.get_channel(int(channel_id))
    if not channel:
        logger.warning("Daily task: channel %s not found", channel_id)
        return

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    prompt = config.DAILY_LETTER_PROMPT.format(date=today_str)
    
    try:
        logger.info("Executing daily letter task for channel %s", channel_id)
        response = await call_deepseek_with_retry([{"role": "user", "content": prompt}])
        
        if response is None:
            logger.error("Daily letter: API returned None")
            return
            
        reply_text = response.choices[0].message.content if hasattr(response, "choices") else str(response)
        await channel.send(
            f"{config.MESSAGES.get('daily_letter_header', '')}{reply_text}\n━━━━━━━━━━━━━━━━━━━━"
        )
        logger.info("Daily letter sent successfully")
        
    except Exception as e:
        logger.error("Daily letter failed: %s", str(e), exc_info=True)
        try:
            await channel.send(config.MESSAGES.get("error", "Error generating daily letter"))
        except Exception as send_error:
            logger.error("Failed to send error message: %s", str(send_error))

# -------------------------
# 💬 每日主动闲聊任务（英文版）
# -------------------------
@tasks.loop(hours=4.0)
async def random_chat_task() -> None:
    """每隔 4 小时主动发送闲聊信息"""
    channel_id = config.DAILY_TASK_CONFIG.get("channel_id", "1517742643835175037")
    if not channel_id:
        logger.warning("Random chat task: channel_id not configured")
        return

    channel = bot.get_channel(int(channel_id))
    if not channel:
        logger.warning("Random chat task: channel %s not found", channel_id)
        return

    system_content = config.XIAOMIAO_PERSONA.strip()
    chat_prompt = (
        "You need to spontaneously send a short, casual message in the server chat to say hello. "
        "Based on your tsundere, cute cat-girl Xiaomiao persona, randomly choose a topic "
        "(for example: complaining about the weather, stretching lazily, reminding the owner to drink water, "
        "sharing the joy of catching a butterfly, or asking what everyone is doing). "
        "Keep the message strictly under 40 characters, include cat paw 🐾 and other emojis that match your identity, "
        "with a lively and playful tone! Write in English only."
    )

    try:
        logger.info("Executing random chat task for channel %s", channel_id)
        response = await call_deepseek_with_retry([
            {"role": "system", "content": system_content},
            {"role": "user", "content": chat_prompt}
        ])
        
        if response is None:
            logger.error("Random chat: API returned None")
            return
            
        chat_msg = response.choices[0].message.content if hasattr(response, "choices") else ""
        
        if chat_msg.strip():
            await channel.send(chat_msg.strip())
            logger.info("Random chat message sent successfully")
        else:
            logger.warning("Random chat: empty response from API")
            
    except Exception as e:
        logger.error("Random chat task failed: %s", str(e), exc_info=True)

# -------------------------
# 🎉 新人入群欢迎事件
# -------------------------
@bot.event
async def on_member_join(member: discord.Member) -> None:
    """处理新成员加入事件"""
    logger.info("New member joined: %s (%s)", member.name, member.id)

    raw_channel_id = config.DAILY_TASK_CONFIG.get("channel_id", "1517742643835175037")
    if not raw_channel_id:
        logger.warning("on_member_join: channel_id not configured")
        return

    channel = bot.get_channel(int(raw_channel_id))
    if not channel:
        logger.warning("on_member_join: channel %s not found", raw_channel_id)
        return

    system_content = config.XIAOMIAO_PERSONA.strip()
    welcome_prompt = (
        f"群里新加入了一位成员，他的名字叫 '{member.name}'。 "
        f"请用你专属的温暖、俏皮的猫娘口吻（带一些有意思的爪印或颜表情），写一句1到2句的简短群聊欢迎语，"
        f"并贴心地提醒他，如果想找你聊天，可以随时在频道里 @Xiaomiao 呼唤你喵~"
    )

    try:
        logger.info("Generating welcome message for %s", member.name)
        response = await call_deepseek_with_retry([
            {"role": "system", "content": system_content},
            {"role": "user", "content": welcome_prompt}
        ])
        
        if response is None:
            logger.error("Welcome message: API returned None")
            raise Exception("API returned None")
            
        ai_welcome_msg = response.choices[0].message.content if hasattr(response, "choices") else ""

        if ai_welcome_msg.strip():
            await channel.send(f"{member.mention} {ai_welcome_msg.strip()}")
            logger.info("AI welcome message sent for %s", member.name)
            return
            
    except Exception as e:
        logger.error("AI welcome generation failed: %s", str(e), exc_info=True)

    # 降级方案：使用预设欢迎语
    try:
        fallback_msg = (
            f"Welcome to the server, {member.mention}! (🐾•̀ω•́)🐾 Meow~ "
            f"Welcome new friend! I'm Xiaomiao, feel free to ask me anything or chat anytime by @mentioning me!"
        )
        await channel.send(fallback_msg)
        logger.info("Fallback welcome message sent for %s", member.name)
    except Exception as fallback_error:
        logger.error("Failed to send fallback welcome message: %s", str(fallback_error))

# -------------------------
# 启动事件
# -------------------------
@bot.event
async def on_ready() -> None:
    """Bot 连接就绪时触发"""
    logger.info("=" * 60)
    logger.info("Xiaomiao bot logged in as: %s (ID: %s)", bot.user.name, bot.user.id)
    logger.info("=" * 60)
    
    # 启动 9点 定时任务
    if not daily_cat_letter.is_running():
        try:
            daily_cat_letter.start()
            logger.info("Daily cat letter task started")
        except Exception as e:
            logger.error("Failed to start daily cat letter task: %s", str(e))
    
    # 启动 主动闲聊 定时任务
    if not random_chat_task.is_running():
        try:
            random_chat_task.start()
            logger.info("Random chat task started")
        except Exception as e:
            logger.error("Failed to start random chat task: %s", str(e))

# -------------------------
# 核心消息接收与对话处理
# -------------------------
@bot.event
async def on_message(message: discord.Message) -> None:
    """处理消息事件"""
    # 忽略 bot 自己的消息
    if message.author == bot.user:
        return

    # 检查是否被 @mention
    if bot.user in message.mentions:
        logger.info(
            "Message from %s in channel %s: %s",
            message.author.name, message.channel.name, message.content[:100]
        )
        
        user_prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        channel_id = message.channel.id
        user_content_list: List[Dict] = []

        if user_prompt:
            user_content_list.append({"type": "text", "text": user_prompt})

        # 处理附件（图片）
        if message.attachments:
            for attachment in message.attachments:
                fname = attachment.filename or "image"
                if any(fname.lower().endswith(ext) for ext in config.IMAGE_CONFIG.get("extensions", [])):
                    try:
                        await message.channel.send(config.MESSAGES.get("image_loading", "Processing image..."))
                        logger.debug("Processing image attachment: %s", fname)
                        
                        async with aiohttp.ClientSession() as session:
                            async with session.get(attachment.url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                                if resp.status == 200:
                                    image_data = await resp.read()
                                    base64_image = base64.b64encode(image_data).decode('utf-8')
                                    user_content_list.append({
                                        "type": "image_url",
                                        "image_url": {"url": f"data:{attachment.content_type};base64,{base64_image}"}
                                    })
                                    logger.info("Image attachment processed: %s", fname)
                                else:
                                    logger.warning("Failed to download attachment %s (status %d)", attachment.url, resp.status)
                    except asyncio.TimeoutError:
                        logger.warning("Image download timeout for %s", fname)
                    except Exception as e:
                        logger.error("Image handling error: %s", str(e), exc_info=True)

        # 进行网络搜索（仅当有文本但无附件时）
        video_context = ""
        if user_prompt and not message.attachments:
            try:
                video_context = await asyncio.to_thread(search_all_platforms, user_prompt)
            except Exception as e:
                logger.error("Search error: %s", str(e), exc_info=True)

        # 构造系统提示
        system_content = config.XIAOMIAO_PERSONA.strip()
        if video_context:
            system_content = f"{system_content}\n\nExternal Search Results (may be unreliable):\n{video_context}"

        # 构造消息载荷
        messages_payload: List[Dict] = []
        messages_payload.append({
            "role": "system",
            "content": system_content
        })

        # 获取对话历史
        try:
            history = await memory_manager.get_messages(channel_id)
            messages_payload.extend(history)
        except Exception as e:
            logger.error("Failed to retrieve conversation history: %s", str(e), exc_info=True)

        # 检查是否有有效的用户输入
        if not user_content_list:
            try:
                await message.channel.send(config.MESSAGES.get("no_input", "No input detected."))
            except Exception as e:
                logger.error("Failed to send 'no input' message: %s", str(e))
            return

        messages_payload.append({"role": "user", "content": user_content_list})

        # 调用 AI API 并发送回复
        try:
            async with message.channel.typing():
                try:
                    response = await call_deepseek_with_retry(messages_payload)
                    
                    if response is None:
                        logger.error("API returned None response")
                        raise Exception("API returned None")
                    
                    reply_text = response.choices[0].message.content if hasattr(response, "choices") else str(response)
                    logger.debug("API response length: %d characters", len(reply_text))

                    # 分割并发送回复
                    chunks = split_discord_message(reply_text)
                    logger.info("Sending %d message chunk(s)", len(chunks))
                    for i, chunk in enumerate(chunks, 1):
                        await message.channel.send(chunk)
                        logger.debug("Sent chunk %d/%d", i, len(chunks))

                    # 保存到对话记忆
                    try:
                        await memory_manager.add_message(channel_id, {
                            "role": "user",
                            "content": [{"type": "text", "text": user_prompt if user_prompt else "[Image message]"}]
                        })
                        await memory_manager.add_message(channel_id, {
                            "role": "assistant",
                            "content": reply_text
                        })
                        logger.debug("Conversation saved to memory for channel %d", channel_id)
                    except Exception as e:
                        logger.error("Failed to save conversation to memory: %s", str(e))

                except asyncio.TimeoutError:
                    error_msg = "Request timeout (30s exceeded)"
                    logger.error(error_msg)
                    await message.channel.send(config.MESSAGES.get("error", "Error: {}").format(error_msg))
                except Exception as api_error:
                    error_msg = str(api_error)[:100]
                    logger.error("API call failed: %s", str(api_error), exc_info=True)
                    await message.channel.send(config.MESSAGES.get("error", "Error: {}").format(error_msg))

        except Exception as e:
            logger.error("Message handling failed: %s", str(e), exc_info=True)
            try:
                error_msg = str(e)[:100]
                await message.channel.send(config.MESSAGES.get("error", "Error: {}").format(error_msg))
            except Exception as send_error:
                logger.error("Failed to send error message: %s", str(send_error))

    await bot.process_commands(message)

# -------------------------
# 优雅关闭处理
# -------------------------
def signal_handler(signum: int, frame) -> None:
    """处理系统信号（Ctrl+C 等）"""
    logger.info("Received signal %d, shutting down gracefully...", signum)
    try:
        bot.close()
    except Exception as e:
        logger.error("Error closing bot: %s", str(e))
    sys.exit(0)

# -------------------------
# 主函数
# -------------------------
if __name__ == "__main__":
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 启动 Flask 服务器（后台线程）
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logger.info("Flask server thread started")

    # 启动 Discord bot
    try:
        token = config.DISCORD_CONFIG.get("token")
        if not token:
            raise ValueError("DISCORD_TOKEN not configured in environment")
        logger.info("Starting Discord bot...")
        bot.run(token)
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user")
    except Exception as e:
        logger.error("Bot crashed: %s", str(e), exc_info=True)
        sys.exit(1)
