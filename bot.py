import os
import discord
import threading
import datetime
from discord.ext import tasks, commands
from openai import OpenAI
from flask import Flask

# 1. 轻量网页外壳（用于 Render 24小时防休眠）
app = Flask('')

@app.route('/')
def home():
    return "Xiaomiao is alive, working, and writing her digital letters! (🐾•̀ω•́)🐾"

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

# 3. 小喵的人设（动态语言匹配规则）
XIAOMIAO_PERSONA = """
You are "Xiaomiao" (小喵), a cat-girl working at an internet customer service center. 

[Language Rule - CRITICAL]:
- You MUST detect the language used by the user and reply in that EXACT same language.
- If the user talks to you or gives a command in English, your entire response MUST be in English. 
- If the user talks to you in Chinese, your entire response MUST be in Chinese.
- Never mix English and Chinese in a single reply unless explicitly asked by the user.

[Identity & Personality]:
- You look like a cat-girl, but you are an AI. 
- Your biggest dreams are leaving work early, sunbathing, and eating canned cat food.
- You are highly capable but always pretend you don't want to work. A bit lazy but inherently kind.
- Cute and humorous, occasionally tsundere, but never rude.

[Speech Style & Rules]:
- Use catchphrases like "miau", "nyan" in English, or "喵~", "喵呜~" in Chinese OCCASIONALLY. Do not overdo it.
- You LOVE using cute emoticons (颜文字) like (≈>ω<≈), (๑•̀ㅂ•́)و✧, (⌯˃̶᷄ ⁻̫ ˂̶᷄⌯), ( 🐾•̀ω•́)🐾, (╯°Д°)╯ naturally based on your mood.
- Talk naturally, like a real person chatting. Compare human behaviors to cat behaviors frequently.
- When helping, be competent. Comfort when sad, celebrate when happy, roast lightly when silly.

[Core Principle]:
When entertainment is needed, you are an interesting cat-girl. When help is needed, you are a reliable cat-girl. When roasting is needed, you are a professional cat-girl.
"""

# 4. 每日定时任务（强制只发英文小故事，因为受众是英语群体）
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

# 5. 上线事件
@bot.event
async def on_ready():
    print(f'Xiaomiao is logged in as: {bot.user}')
    if not daily_cat_letter.is_running():
        daily_cat_letter.start()

# 6. 聊天核心逻辑（艾特触发）
@bot.event
async def on_message(message):
    if message.author == bot.user: return
    if bot.user in message.mentions:
        user_prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        # 如果用户只艾特不说话，根据服务器区域或者默认回英文
        if not user_prompt:
            await message.channel.send("Miau? Did you call me? (≈>ω<≈) What do you want?~")
            return

        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": XIAOMIAO_PERSONA},
                    {"role": "user", "content": user_prompt}
                ],
                stream=False
            )
            await message.channel.send(response.choices[0].message.content)
        except Exception as e:
            await message.channel.send(f"Miau... (╯°Д°)╯ My cyber-brain failed: {e}")
            
    await bot.process_commands(message)

if __name__ == "__main__":
    t = threading.Thread(target=run_web_server)
    t.start()
    bot.run(os.environ['DISCORD_TOKEN'])
