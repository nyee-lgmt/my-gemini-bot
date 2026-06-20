import os
import discord
from openai import OpenAI

# 初始化 Discord 机器人
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# 初始化 DeepSeek 客户端（它在代码里用 OpenAI 协议完美兼容）
client = OpenAI(
    api_key=os.environ['DEEPSEEK_API_KEY'], 
    base_url="https://api.deepseek.com"
)

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
            # 开启 deepseek-chat 聊天对话
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "user", "content": user_prompt}
                ],
                stream=False
            )
            await message.channel.send(response.choices[0].message.content)
        except Exception as e:
            await message.channel.send(f"哎呀，调用 DeepSeek 时出错了：{e}")

# 启动机器人
bot.run(os.environ['DISCORD_TOKEN'])
