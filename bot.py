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
    return "Xiaomiao's Video Radar (YT + Bilibili) is fully operational! (🐾•̀ω•́)🐾"

def run_web_server():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# 2. 初始化 Discord 机器人
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 初始化 DeepSeek 客户端（共用同一个 Token）
client = OpenAI(
    api_key=os.environ['DEEPSEEK_API_KEY'], 
    base_url="https://api.deepseek.com"
)

# 3. 小喵的人设（强化B站+YT视频多版本攻略对比）
XIAOMIAO_PERSONA = """
You are "Xiaomiao" (小喵), a highly capable, internet-savvy cat-girl working at an internet customer service center. 

[Language Rule - CRITICAL]:
- You MUST detect the language used by the user and reply in that EXACT same language (English or Chinese).

[Video Strategy & Version Analysis Rule - STRICT]:
- When provided with YouTube and Bilibili search results, you MUST act as a professional gaming analyst.
- You CANNOT just give one vague answer. You MUST organize the data into clear "Versions/Builds/Options" (多个版本方案) for the user to choose from.
- For example: Provide "Option 1: Budget/F2P Friendly Version (平民/性价比版)", "Option 2: High-End/Meta Version (高配/主流毕业版)", etc.
- Clearly analyze the pros, cons, and required resources for EACH option.
- Explicitly tell the user: "Here are the best versions based on YouTube and Bilibili data. Choose the one that fits you best! 🐾"
- Always present the raw video URLs/links next to the options so the user can watch them.
- Keep your witty, tsundere cat-girl personality intact!
"""

# 4. 升级版辅助函数：全网三重搜索（YouTube + Bilibili + 全网文本）
def search_all_platforms(query):
    search_context = ""
    try:
        with DDGS() as ddgs:
            # 1. 定向抓取 哔哩哔哩 (Bilibili) 视频攻略
            bili_query = f"{query} site:bilibili.com"
            bili_results = [r for r in ddgs.text(bili_query, max_results=3)]
            if bili_results:
                search_context += "\n=== BILIBILI VIDEO GUIDES FOUND ===\n"
                for i, r in enumerate(bili_results, 1):
                    search_context += f"Bilibili [{i}]:\nTitle: {r['title']}\nLink: {r['href']}\nSnippet: {r['body']}\n\n"
            
            # 2. 定向抓取 YouTube 视频攻略
            yt_query = f"{query} site:youtube.com"
            yt_results = [r for r in ddgs.text(yt_query, max_results=3)]
            if yt_results:
                search_context += "=== YOUTUBE VIDEO GUIDES FOUND ===\n"
                for i, r in enumerate(yt_results, 1):
                    search_context += f"YouTube [{i}]:\nTitle: {r['title']}\nLink: {r['href']}\nSnippet: {r['body']}\n\n"
            
            # 3. 抓取全网（如论坛、新闻）最新2026年数据做补充
            web_query = f"{query} guide 2026"
            web_results = [r for r in ddgs.text(web_query, max_results=2)]
            if web_results:
                search_context += "=== WEB DISCUSSIONS & LATEST METRICS ===\n"
                for i, r in enumerate(web_results, 1):
                    search_context += f"Web [{i}]:\nTitle: {r['title']}\nDetails: {r['body']}\n\n"
                    
            if not search_context:
                return "No video or web search results found."
            return search_context
    except Exception as e:
        print(f"Multi-platform search error: {e}")
        return ""

# 5. 每日定时任务（纯英网络猫咪来信不变）
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

# 6. 核心逻辑（图片解析 + 三重复合联网搜索 + 多版本输出）
@bot.event
async def on_message(message):
    if message.author == bot.user: return
    
    if bot.user in message.mentions:
        user_prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        messages_payload = []
        user_content = []
        
        if user_prompt:
            user_content.append({"type": "text", "text": user_prompt})
            
        # 图片识别部分保持不动
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

        # 触发联网搜索：混合 B站 与 YouTube 数据
        video_context = ""
        if user_prompt and not message.attachments:
            print(f"Xiaomiao is hunting Bilibili & YT for: {user_prompt}")
            video_context = search_all_platforms(user_prompt)
            
        messages_payload.append({
            "role": "system", 
            "content": f"{XIAOMIAO_PERSONA}\n{video_context}"
        })
        
        if not user_content:
            await message.channel.send("Miau? Did you call me? (≈>ω<≈) Tell me what strategy or guide you want to find!~")
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
