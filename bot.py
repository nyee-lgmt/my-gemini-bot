import os
import discord
from discord.ext import commands
from google import genai

# 从 Render 云端安全读取密钥（不需要在代码里明文写出来了）
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# 初始化 Gemini 客户端
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# 初始化 Discord 机器人权限
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"=========================================")
    print(f"🎉 机器人成功在云端上线啦！")
    print(f"🤖 名字: {bot.user.name}")
    print(f"=========================================")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user.mentioned_in(message):
        prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if not prompt:
            await message.channel.send("找我有什么事吗？在 @我 的时候顺便输入问题吧！")
            return

        async with message.channel.typing():
            try:
                # 调用最新的 Gemini 2.5 Flash
                response = ai_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                )
                await message.reply(response.text)
            except Exception as e:
                await message.reply(f"❌ 哎呀，调用 Gemini 时出错了: {str(e)}")

    await bot.process_commands(message)

bot.run(DISCORD_TOKEN)
