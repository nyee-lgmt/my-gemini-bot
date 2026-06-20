import os
import discord
from openai import OpenAI

# Initialize Discord Bot
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# Initialize DeepSeek Client via OpenAI protocol
client = OpenAI(
    api_key=os.environ['DEEPSEEK_API_KEY'], 
    base_url="https://api.deepseek.com"
)

@bot.event
async def on_ready():
    print(f'Bot is logged in as: {bot.user}')

@bot.event
async def on_message(message):
    # Ignore messages sent by the bot itself
    if message.author == bot.user:
        return

    # Reply only when the bot is mentioned
    if bot.user in message.mentions:
        # Strip the mention tag to get the clean user prompt
        user_prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        if not user_prompt:
            await message.channel.send("How can I help you today?")
            return

        try:
            # Generate response using deepseek-chat model
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "user", "content": user_prompt}
                ],
                stream=False
            )
            await message.channel.send(response.choices[0].message.content)
        except Exception as e:
            await message.channel.send(f"Oops, something went wrong while calling the AI: {e}")

# Start the bot
bot.run(os.environ['DISCORD_TOKEN'])
