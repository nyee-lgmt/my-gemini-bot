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

# 1. 轻量网页外壳
app = Flask('')
@app.route('/')
def home(): 
    return "Xiaomiao's Smart-感知 Time Filter Video Radar is fully active! (🐾•̀ω•́)🐾"

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

# 3. 小喵的人设
XIAOMIAO_PERSONA = """
You are "Xiaomiao" (小喵), a highly capable, internet-savvy cat-girl working at an internet customer service center. 

[Language Rule - CRITICAL]:
- You MUST detect the language used by the user and reply in that EXACT same language (English or Chinese).

[Video Strategy & Version Analysis Rule - STRICT]:
- Below your persona, you will be provided with real-time web and video search results.
- You MUST rely on these provided search results to answer questions about gaming updates, streams, or news.
- Organize the data into clear "Versions/Builds/Options" (多个版本方案) for the user to choose from if applicable.
- Always include the raw video URLs/links provided in the search results so the user can watch them!
- Keep your witty, tsundere cat-girl personality intact.
"""

# 4. 核心升级：智能感知分流搜索函数
def search_all_platforms(query):
    search_context = ""
    
    # 🧠 智能判断：如果用户问的是“最新”、“前瞻”、“攻略”等时效性极强的词，自动追加 2026 年份过滤老视频
    # 如果用户问的是历史老梗、当年的事情（未触发这些词），则保留原样搜索，允许搜到多年前的资料
    is_latest_query = any(keyword in query for keyword in ["最新", "前瞻", "攻略", "版本", "活动", "new", "latest", "guide"])
    search_query = f"{query} 2026" if is_latest_query else query
    
    try:
        with DDGS() as ddgs:
            # 1. 抓取 哔哩哔哩 (Bilibili) 视频
            bili_query = f"{search_query} site:bilibili.com"
            bili_results = [r for r in ddgs.text(bili_query, max_results=3)]
            if bili_results:
                search_context += f"\n=== BILIBILI VIDEO GUIDES (Target: {search_query}) ===\n"
                for i, r in enumerate(bili_results, 1):
                    search_context += f"Bilibili [{i}]:\nTitle: {r['title']}\nLink: {r['href']}\nSnippet: {r['body']}\n\n"
            
            # 2. 抓取 YouTube 视频
            yt_query = f"{search_query} site:youtube.com"
            yt_results = [r for r in ddgs.text(yt_query, max_results=3)]
            if yt_results:
                search_context += f"=== YOUTUBE VIDEO GUIDES (Target: {search_query}) ===\n"
                for i, r in enumerate(yt_results, 1):
                    search_context += f"YouTube [{i}]:\nTitle: {r['title']}\nLink: {r['href']}\nSnippet: {r['body']}\n\n"
            
            # 3. 抓取全网最新报道/文字讨论作为补充
            web_query = f"{query} latest news 2026" if is_latest_query else query
            web_results = [r for r in ddgs.text(web_query, max_results=2)]
            if web_results:
                search_context += "=== WEB NEWS & DISCUSSIONS ===\n"
                for i, r in enumerate(web_results, 1):
                    search_context += f"Web [{i}]:\nTitle: {r['title']}\nDetails: {r['body']}\n\n"
                    
            if not search_context:
                return "No search results found for this topic."
            return search_context
    except Exception as e:
        print(f"Multi-platform search error: {e}")
        return ""

# 5. 每日定时任务（纯英故事）
@tasks.loop(time=datetime.time(hour=1, minute=0, tzinfo=datetime.timezone.utc))
async def daily_cat_letter():
    CHANNEL_ID = 1517742643835175037  
    channel = bot.get_channel(CHANNEL_ID) 
    if not channel: return
    
    prompt = "Write a short, daily journal entry in English. Title: 'Letters from a Cat Stuck on the Internet'. Persona: Xiaomiao, a cat trapped inside the digital network. Length: 80-200 words. English ONLY. Use emoticons."
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        await channel.send(f"📬 **New Message Received...**\n━━━━━━━━━━━━━━━━━━━━\n{response.choices[0].message.content}\n━━━━━━━━━━━━━━━━━━━━")
    except Exception as e: 
        print(f"Daily letter failed: {e}")

@bot.event
async def on_ready():
    print(f'Xiaomiao is logged in as: {bot.user}')
    if not daily_cat_letter.is_running(): 
        daily_cat_letter.start()

# 6. 聊天与多模态核心逻辑
@bot.event
async def on_message(message):
    if message.author == bot.user: return
    
    if bot.user in message.mentions:
        user_prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        messages_payload = []
        user_content = []
        
        if user_prompt:
            user_content.append({"type": "text", "text": user_prompt})
            
        # 图片附件识别保持
        if message.attachments:
            for attachment in message.attachments:
                if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                    await message.channel.send("呜喵？正在用肉垫解析图片... ( 🐾•̀ω•́)🐾")
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

        # 触发搜索（智能感知关键词，防穿越漏洞）
        video_context = ""
        if user_prompt and not message.attachments:
            print(f"Xiaomiao is evaluating query timeline for: {user_prompt}")
            video_context = search_all_platforms(user_prompt)
            
        messages_payload.append({
            "role": "system", 
            "content": f"{XIAOMIAO_PERSONA}\n{video_context}"
        })
        
        if not user_content:
            await message.channel.send("Miau? Did you call me? (≈>ω<≈) Tell me what you want to check!~")
            return
            
        if not user_prompt and message.attachments:
            user_content.append({"type": "text", "text": "What do you think of this image?"})
            
        messages_payload.append({"role": "user", "content": user_content})

        try:
            async with message.channel.typing():
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages_payload,
                    stream=False
                )
                await message.channel.send(response.choices[0].message.content)
        except Exception as e:
            await message.channel.send(f"Miau... (╯°Д°)╯ Brain error: {e}")
            
    await bot.process_commands(message)

if __name__ == "__main__":
    threading.Thread(target=run_web_server).start()
    bot.run(os.environ['DISCORD_TOKEN'])
