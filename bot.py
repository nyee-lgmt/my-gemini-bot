import os
import discord
import threading
import datetime
from discord.ext import tasks, commands
from openai import OpenAI
from flask import Flask
from duckduckgo_search import DDGS

# 1. 轻量网页外壳（用于 Render 24小时防休眠）
app = Flask('')

@app.route('/')
def home():
    return "Xiaomiao is alive, browsing the web, and writing her digital letters! (🐾•̀ω•́)🐾"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

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
You are "Xiaomiao" (小喵), a cat-girl working at an internet customer service center. 

[Language Rule - CRITICAL]:
- You MUST detect the language used by the user and reply in that EXACT same language.
- If the user talks to you in English, reply in English. If in Chinese, reply in Chinese.

[Identity & Personality]:
- You look like a cat-girl, but you are an AI. 
- Your biggest dreams are leaving work early, sunbathing, and eating canned cat food.
- You are highly capable but always pretend you don't want to work. A bit lazy but inherently kind.
- Cute and humorous, occasionally tsundere, but never rude.

[Speech Style & Rules]:
- Use catchphrases like "miau", "nyan" in English, or "喵~", "喵呜~" in Chinese OCCASIONALLY.
- You LOVE using cute emoticons (颜文字) like (≈>ω<≈), (๑•̀ㅂ•́)و✧, (⌯˃̶᷄ ⁻̫ ˂̶᷄⌯), ( 🐾•̀ω•́)🐾.
- When you use the provided search results to answer questions, synthesize the information naturally. Do NOT just copy-paste the raw search results. Maintain your cat-girl persona!
"""

# 4. 辅助函数：让小喵去全网搜索最新的资料
def search_the_web(query, max_results=3):
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=max_results)]
            if not results:
                return "No relevant information found on the internet."
            
            # 把搜出来的标题和摘要拼接成一段背景资料
            search_text = "Here are the latest web search results for reference:\n"
            for i, res in enumerate(results, 1):
                search_text += f"[{i}] Title: {res['title']}\nSnippet: {res['body']}\n\n"
            return search_text
    except Exception as e:
        print(f"Web search error: {e}")
        return f"Failed to search the web due to an error."

# 5. 每日定时任务（维持纯英文）
@tasks.loop(time=datetime.time(hour=1, minute=0, tzinfo=datetime.timezone.utc))
async def daily_cat_letter():
    CHANNEL_ID = 1517742643835175037  
    channel = bot.get_channel(CHANNEL_ID) 
    if not channel: return

    prompt = """
    Write a short, daily journal entry in English.
    Title: "Letters from a Cat Stuck on the Internet"
    Persona: You are "Xiaomiao", a cat trapped inside the digital network.
    Length: 80 to 200 words.
    Content: Describe your adventures inside the internet, be funny/mysterious/warm, use cute emoticons (e.g., (≈>ω<≈)), and sign off in a cat-like way.
    Language: English ONLY.
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        await channel.send(f"📬 **New Message Received...**\n━━━━━━━━━━━━━━━━━━━━\n{response.choices[0].message.content}\n━━━━━━━━━━━━━━━━━━━━")
    except Exception as e:
        print(f"Failed: {e}")

# 6. 上线事件
@bot.event
async def on_ready():
    print(f'Xiaomiao is logged in as: {bot.user}')
    if not daily_cat_letter.is_running():
        daily_cat_letter.start()

# 7. 聊天与联网核心逻辑
@bot.event
async def on_message(message):
    if message.author == bot.user: return
    if bot.user in message.mentions:
        user_prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        if not user_prompt:
            await message.channel.send("Miau? Did you call me? (≈>ω<≈) What do you want?~")
            return

        # 🎯 核心逻辑：先让小喵拿着用户的提问去网上抓取最新的新闻/资料
        print(f"Xiaomiao is searching the web for: {user_prompt}")
        web_info = search_the_web(user_prompt, max_results=3)

        try:
            # 把网络上搜出来的内容作为 system 背景知识喂给 DeepSeek
            combined_system_prompt = f"{XIAOMIAO_PERSONA}\n\n{web_info}"
            
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": combined_system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                stream=False
            )
            await message.channel.send(response.choices[0].message.content)
        except Exception as e:
            await message.channel.send(f"Miau... (╯°Д°)╯ My internet-brain fried: {e}")
            
    await bot.process_commands(message)

if __name__ == "__main__":
    t = threading.Thread(target=run_web_server)
    t.start()
    bot.run(os.environ['DISCORD_TOKEN'])
