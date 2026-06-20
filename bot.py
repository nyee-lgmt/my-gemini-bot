import os
import discord
from google import genai

# 初始化 Discord 机器人
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# 初始化最新的 Gemini 客户端
# 它会自动读取你在 Render 里填写的 GEMINI_API_KEY
client = genai.Client()

@bot.event
async def on_ready():
    print(f'机器人已登录: {bot.user}')

@bot.event
async def on_message(message):
    # 别理机器人自己发的消息
    if message.author == bot.user:
        return

    # 只有当别人 @ 机器人时才回复
    if bot.user in message.mentions:
        # 去掉 @ 机器人的文本，拿到纯提问
        user_prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        if not user_prompt:
            await message.channel.send("找我有什么事吗？")
            return

        try:
            # 使用最新且最稳定的 gemini-2.5-flash 模型
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=user_prompt,
            )
            await message.channel.send(response.text)
        except Exception as e:
            await message.channel.send(f"哎呀，调用 Gemini 时出错了：{e}")

# 启动机器人
bot.run(os.environ['DISCORD_TOKEN'])
