import os
import discord
import threading
import datetime
import aiohttp
import base64
from discord.ext import tasks, commands
from openai import OpenAI
from flask import Flask
from duckduckgo_search import DDGS

# 📥 1. 导入你的新版 config 模块
import config

# 🚨 【核心满足】：触发校验函数。如果缺少 API_KEY 或 TOKEN，程序会在启动的第一秒报错，避免带病运行。
config.validate_required_envs()

# 2. 轻量网页外壳 - 适配新版配置字典
app = Flask('')
@app.route('/')
def home(): 
    return config.MESSAGES['web_home']

def run_web_server():
    app.run(
        host=config.FLASK_CONFIG['host'], 
        port=config.FLASK_CONFIG['port']
    )

# 3. 初始化 Discord 机器人 - 适配新版配置字典
intents = discord.Intents.default()
intents.message_content = config.DISCORD_CONFIG['message_content']
bot = commands.Bot(
    command_prefix=config.DISCORD_CONFIG['command_prefix'], 
    intents=intents
)

# 初始化 DeepSeek 客户端 - 适配新版配置字典
client = OpenAI(
    api_key=config.DEEPSEEK_CONFIG['api_key'], 
    base_url=config.DEEPSEEK_CONFIG['base_url']
)

# 🧠 低消耗会话记忆存储库 { channel_id: [messages] }
conversation_history = {}

# 4. 智能感知分流搜索函数 - 适配新版配置字典
def search_all_platforms(query):
    # 读取你配置的关键词列表
    SEARCH_KEYWORDS = config.SEARCH_CONFIG['keywords']
    LATEST_KEYWORDS = config.SEARCH_CONFIG['latest_keywords']
    
    # 如果用户的消息完全不包含搜索特征词，直接关闭联网，防止干扰上下文
    if not any(kw in query for kw in SEARCH_KEYWORDS):
        return ""
        
    search_context = ""
    is_latest_query = any(keyword in query for keyword in LATEST_KEYWORDS)
    search_query = f"{query} 2026" if is_latest_query else query
    
    try:
        with DDGS() as ddgs:
            # 抓取 Bilibili 视频小抄
            bili_max = config.SEARCH_CONFIG['bilibili_max_results']
            bili_results = [r for r in ddgs.text(f"{search_query} site:bilibili.com", max_results=bili_max)]
            if bili_results:
                search_context += f"\n=== BILIBILI VIDEO GUIDES ===\n"
                for i, r in enumerate(bili_results, 1):
                    search_context += f"Bilibili [{i}]:\nTitle: {r['title']}\nLink: {r['href']}\nSnippet: {r['body']}\n\n"
            
            # 抓取 YouTube 视频小抄
            yt_max = config.SEARCH_CONFIG['youtube_max_results']
            yt_results = [r for r in ddgs.text(f"{search_query} site:youtube.com", max_results=yt_max)]
            if yt_results:
                search_context += f"=== YOUTUBE VIDEO GUIDES ===\n"
                for i, r in enumerate(yt_results, 1):
                    search_context += f"YouTube [{i}]:\nTitle: {r['title']}\nLink: {r['href']}\nSnippet: {r['body']}\n\n"
                    
            if not search_context:
                return config.MESSAGES['search_notice'].format(query)
            return search_context
    except Exception as e:
        print(f"Search error: {e}")
        return ""

# 5. 每日定时任务 - 适配新版配置字典
@tasks.loop(time=datetime.time(
    hour=config.DAILY_TASK_CONFIG['hour'], 
    minute=config.DAILY_TASK_CONFIG['minute'], 
    tzinfo=datetime.timezone.utc
))
async def daily_cat_letter():
    channel = bot.get_channel(config.DAILY_TASK_CONFIG['channel_id']) 
    if not channel: return
    
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    prompt = config.DAILY_LETTER_PROMPT.format(date=today_str)
    try:
        response = client.chat.completions.create(
            model=config.DEEPSEEK_CONFIG['model'],
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        await channel.send(f"{config.MESSAGES['daily_letter_header']}\n━━━━━━━━━━━━━━━━━━━━\n{response.choices[0].message.content}\n━━━━━━━━━━━━━━━━━━━━")
    except Exception as e: 
        print(f"Daily letter failed: {e}")

@bot.event
async def on_ready():
    print(f"Xiaomiao is logged in as: {bot.user}")
    if not daily_cat_letter.is_running(): 
        daily_cat_letter.start()

# 6. 聊天与低消耗记忆核心逻辑
@bot.event
async def on_message(message):
    if message.author == bot.user: return
    
    if bot.user in message.mentions:
        user_prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        channel_id = message.channel.id
        if channel_id not in conversation_history:
            conversation_history[channel_id] = []
            
        messages_payload = []
        user_content = []
        
        if user_prompt:
            user_content.append({"type": "text", "text": user_prompt})
            
        # 多模态图片解析维护
        if message.attachments:
            for attachment in message.attachments:
                if any(attachment.filename.lower().endswith(ext) for ext in config.IMAGE_CONFIG['extensions']):
                    await message.channel.send(config.MESSAGES['image_loading'])
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(attachment.url) as resp:
                                if resp.status == 200:
                                    image_data = await resp.read()
                                    base64_image = base64.b64encode(image_data).decode('utf-8')
                                    user_content.append({
                                        "type": "image_url",
                                        "image_url": {"url": f"data:{attachment.content_type};base64,{base64_image}"}
                                    })
                    except Exception as e:
                        print(f"Image error: {e}")

        # 触发搜索策略分流
        video_context = ""
        if user_prompt and not message.attachments:
            video_context = search_all_platforms(user_prompt)
            
        # 组装 Payload：系统设定（包含搜索结果）
        messages_payload.append({
            "role": "system", 
            "content": f"{config.XIAOMIAO_PERSONA}\n{video_context}"
        })
        
        # 🧠 低消耗记忆核心：追加上历史会话
        messages_payload.extend(conversation_history[channel_id])
        
        if not user_content:
            await message.channel.send(config.MESSAGES['no_input'])
            return
            
        # 拼接用户最新的一轮输入
        messages_payload.append({"role": "user", "content": user_content})

        try:
            async with message.channel.typing():
                response = client.chat.completions.create(
                    model=config.DEEPSEEK_CONFIG['model'],
                    messages=messages_payload,
                    stream=False
                )
                reply_text = response.choices[0].message.content
                await message.channel.send(reply_text)
                
                # 💾 将这一轮的交互塞入缓存
                conversation_history[channel_id].append({"role": "user", "content": user_prompt})
                conversation_history[channel_id].append({"role": "assistant", "content": reply_text})
                
                # ✂️ Token严格裁剪：获取配置中的最大保留轮数并裁剪
                max_len = config.MEMORY_CONFIG['max_history_rounds'] * 2
                conversation_history[channel_id] = conversation_history[channel_id][-max_len:]
                
        except Exception as e:
            await message.channel.send(config.MESSAGES['error'].format(e))
            
    await bot.process_commands(message)

if __name__ == "__main__":
    threading.Thread(target=run_web_server).start()
    bot.run(config.DISCORD_CONFIG['token'])
