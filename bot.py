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

# 📥 完美套用：导入你写的 config 配置
import config

# 1. 轻量网页外壳
app = Flask('')
@app.route('/')
def home(): 
    return config.MESSAGES['web_home']

def run_web_server():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# 2. 初始化 Discord 机器人
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 初始化 DeepSeek 客户端
client = OpenAI(
    api_key=os.environ['DEEPSEEK_API_KEY'], 
    base_url="https://api.deepseek.com"
)

# 🧠 核心：低消耗会话记忆存储库 { channel_id: [messages] }
conversation_history = {}

# 3. 智能感知分流搜索函数
def search_all_platforms(query):
    SEARCH_KEYWORDS = ["搜", "查", "最新", "前瞻", "攻略", "版本", "活动", "什么", "怎么", "哪个", "new", "latest", "guide", "vs"]
    
    # 日常闲聊（不含这些词）直接拒绝联网，防止干扰和浪费 Token
    if not any(kw in query for kw in SEARCH_KEYWORDS):
        return ""
        
    search_context = ""
    is_latest_query = any(keyword in query for keyword in ["最新", "前瞻", "攻略", "版本", "活动", "new", "latest", "guide"])
    search_query = f"{query} 2026" if is_latest_query else query
    
    try:
        with DDGS() as ddgs:
            # 抓取 Bilibili
            bili_results = [r for r in ddgs.text(f"{search_query} site:bilibili.com", max_results=2)]
            if bili_results:
                search_context += f"\n=== BILIBILI VIDEO GUIDES ===\n"
                for i, r in enumerate(bili_results, 1):
                    search_context += f"Bilibili [{i}]:\nTitle: {r['title']}\nLink: {r['href']}\nSnippet: {r['body']}\n\n"
            
            # 抓取 YouTube
            yt_results = [r for r in ddgs.text(f"{search_query} site:youtube.com", max_results=2)]
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

# 4. 每日定时任务
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
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        await channel.send(f"{config.MESSAGES['daily_letter_header']}{response.choices[0].message.content}\n━━━━━━━━━━━━━━━━━━━━")
    except Exception as e: 
        print(f"Daily letter failed: {e}")

@bot.event
async def on_ready():
    print(f'Xiaomiao is logged in as: {bot.user}')
    if not daily_cat_letter.is_running(): 
        daily_cat_letter.start()

# 5. 聊天与记忆核心逻辑
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
            
        # 图片附件识别
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

        # 触发联网搜索
        video_context = ""
        if user_prompt and not message.attachments:
            video_context = search_all_platforms(user_prompt)
            
        # 组装 Payload：系统人设 + 搜索小抄
        messages_payload.append({
            "role": "system", 
            "content": f"{config.XIAOMIAO_PERSONA}\n{video_context}"
        })
        
        # 🧠 低消耗记忆核心：把该频道之前存的最近几轮历史对话塞给大模型
        messages_payload.extend(conversation_history[channel_id])
        
        if not user_content:
            await message.channel.send(config.MESSAGES['no_input'])
            return
            
        # 把用户当前这一轮的输入放最后
        messages_payload.append({"role": "user", "content": user_content})

        try:
            async with message.channel.typing():
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages_payload,
                    stream=False
                )
                reply_text = response.choices[0].message.content
                await message.channel.send(reply_text)
                
                # 💾 记忆更新：把这一轮的一问一答存入内存
                conversation_history[channel_id].append({"role": "user", "content": user_prompt})
                conversation_history[channel_id].append({"role": "assistant", "content": reply_text})
                
                # ✂️ Token严格控制：根据 config 配置剪裁记忆，只留最近 N 轮，多的自动忘记！
                max_len = config.MEMORY_CONFIG['max_history_rounds'] * 2
                conversation_history[channel_id] = conversation_history[channel_id][-max_len:]
                
        except Exception as e:
            await message.channel.send(config.MESSAGES['error'].format(e))
            
    await bot.process_commands(message)

if __name__ == "__main__":
    threading.Thread(target=run_web_server).start()
    bot.run(os.environ['DISCORD_TOKEN'])
