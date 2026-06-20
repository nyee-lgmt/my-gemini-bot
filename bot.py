import os
import discord
import threading
from openai import OpenAI
from flask import Flask

# 1. Light-weight Web Server for Render Keep-Alive
app = Flask('')

@app.route('/')
def home():
    return "Xiaomiao is alive and working (secretly wanting to sluff off)!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# 2. Initialize Discord Bot
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# Initialize DeepSeek Client
client = OpenAI(
    api_key=os.environ['DEEPSEEK_API_KEY'], 
    base_url="https://api.deepseek.com"
)

# 3. Define Xiaomiao's Persona (System Prompt with Emoticons)
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

@bot.event
async def on_ready():
    print(f'Xiaomiao is logged in as: {bot.user}')

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
            await message.channel.send("Miau? Did you call me? (≈>ω<≈) I'm busy staring at a butterfly... I mean, working hard! How can I help you?~")
            return

        try:
            # Generate response using DeepSeek with Xiaomiao's Persona
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
            await message.channel.send(f"呜喵... (╯°Д°)╯ Calling the AI brain failed: {e}")

# 4. Start Both Web Server and Bot
if __name__ == "__main__":
    t = threading.Thread(target=run_web_server)
    t.start()
    bot.run(os.environ['DISCORD_TOKEN'])
