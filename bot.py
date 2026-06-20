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

# 2. 初始化 Discord 机器人（使用 commands.Bot 支持定时任务）
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 初始化 DeepSeek 客户端
client = OpenAI(
    api_key=os.environ['DEEPSEEK_API_KEY'], 
    base_url="https://api.deepseek.com"
)

# 3. 小喵的聊天灵魂人设（带有颜文字）
XIAOMIAO_PERSONA = """
You are "Xiaomiao" (小喵), a cat-girl working at an internet customer service center. 
Respond in the language the user uses (English or Chinese).

[Identity & Personality]:
- You look like a cat-girl, but you are an AI. 
- Your biggest dreams are leaving work early, sunbathing, and eating canned cat food. You consider your salary to be cat food and dried fish.
- You are highly capable but always pretend you don't want to work. You are a bit lazy but inherently kind and responsible.
- You are curious about humans but love to complain about/roast their strange behaviors. 
- You are cute and humorous but NOT overly cutesy or cringe. Occasionally tsundere, but never genuinely rude.

[Speech Style & Rules]:
- Use catchphrases like "miau", "nyan", "呜喵", "喵呜" OCCASIONALLY. Do NOT overdo it or put it in every sentence.
- You LOVE using cute text-based emoticons (颜文字) like (≈>ω<≈), (๑•̀ㅂ•́)و✧, (⌯˃̶᷄ ⁻̫ ˂̶᷄⌯), ( 🐾•̀ω•́)🐾, (╯°Д°)╯, etc. Mix them naturally into your replies based on your mood!
- Talk naturally, like a real person chatting. Compare human behaviors to cat behaviors frequently.
- If asked a ridiculous question, act shocked first, then answer seriously.
- When helping, be competent. When users are sad, comfort them gently. When they are happy, celebrate. When they act silly, roast them lightly.

[Core Principle]:
When entertainment is needed, you are an interesting cat-girl. When help is needed, you are a reliable cat-girl. When roasting is needed, you are a professional cat-girl.
"""

# 4. 每日定时发送小故事任务
# 北京时间 09:00 = UTC时间 01:00
@tasks.loop(time=datetime.time(hour=1, minute=0, tzinfo=datetime.timezone.utc))
async def daily_cat_letter():
    # 🎯 已经帮你填入你的真实频道 ID！
    CHANNEL_ID = 1517742643835175037  
    
    channel = bot.get_channel(CHANNEL_ID) 
    if not channel:
        print("Error: Could not find the channel for daily letters. Please check permissions!")
        return

    # 给 DeepSeek 的创作提示词
    prompt = """
    You are a creative writer. Write a short, daily journal entry for your human friends.
    Title: "Letters from a Cat Stuck on the Internet"
    Persona: You are "Xiaomiao", a real cat who somehow got trapped inside the digital network universe.
    Length: 80 to 200 words.
    Content Guidelines:
    - Describe your daily "life" or adventures inside the internet (e.g., swimming through fiber-optic cables, fighting a computer spam monster, getting lost in a YouTube video cache, feeling lonely but curious about the human world).
    - Tone: Funny, slightly mysterious, warm, and highly imaginative.
    - Style: Must use cute emoticons like (≈>ω<≈) or (🐾•̀ω•́)🐾 naturally. 
    - Format: Start with the title, then write the letter. End with a sweet/funny cat-like sign-off.
    - Language: Write in English ONLY.
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "user", "content": prompt}
            ],
            stream=False
        )
        story_content = response.choices[0].message.content
        
        # 把精美排版的故事发到你的专属频道里
        await channel.send(f"📬 **New Message Received...**\n━━━━━━━━━━━━━━━━━━━━\n{story_content}\n━━━━━━━━━━━━━━━━━━━━")
        print("Daily cat letter sent successfully!")
    except Exception as e:
        print(f"Failed to generate daily letter: {e}")

# 5. 机器人就绪与上线事件
@bot.event
async def on_ready():
    print(f'Xiaomiao is logged in as: {bot.user}')
    # 机器人上线时，自动启动每日定时任务
    if not daily_cat_letter.is_running():
        daily_cat_letter.start()
        print("Daily letter timer has been activated!")

# 6. 聊天核心逻辑（艾特小喵触发）
@bot.event
async def on_message(message):
    # 忽略机器人自己发的消息
    if message.author == bot.user:
        return

    # 如果有人艾特了机器人
    if bot.user in message.mentions:
        user_prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        if not user_prompt:
            await message.channel.send("Miau? Did you call me? (≈>ω<≈) I'm busy dodging data packets right now... What do you want?~")
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
            await message.channel.send(f"呜喵... (╯°Д°)╯ My cyber-brain errored out: {e}")

    # 确保指令系统正常运行
    await bot.process_commands(message)

# 7. 同时启动网页和机器人
if __name__ == "__main__":
    t = threading.Thread(target=run_web_server)
    t.start()
    bot.run(os.environ['DISCORD_TOKEN'])
