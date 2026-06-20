import os
import discord
import threading
from openai import OpenAI
from flask import Flask

# 1. 创建一个超轻量的网页服务器，让 Render 以为这是一个网站
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run_web_server():
    # 绑定 Render 默认的端口号，如果没有就用 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# 2. 初始化 Discord 机器人
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# 初始化 DeepSeek 客户端
client = OpenAI(
    api_key=os.environ['DEEPSEEK_API_KEY'], 
    base_url="https://api.deepseek.com"
)

@bot.event
async def on_ready():
    print(f'Bot is logged in as: {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user in message.mentions:
        user_prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        if not user_prompt:
            await message.channel.send("How can I help you today?")
            return

        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": user_prompt}],
                stream=False
            )
            await message.channel.send(response.choices[0].message.content)
        except Exception as e:
            await message.channel.send(f"Oops, something went wrong: {e}")

# 3. 同时启动网页和机器人
if __name__ == "__main__":
    # 用另一个线程悄悄在后台运行网页，防止堵塞机器人
    t = threading.Thread(target=run_web_server)
    t.start()
    
    # 启动机器人
    bot.run(os.environ['DISCORD_TOKEN'])
