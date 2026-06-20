import os

# Flask Web 服务器配置
FLASK_CONFIG = {
    'host': '0.0.0.0',
    'port': int(os.environ.get("PORT", 8080))
}

# DeepSeek API 配置
DEEPSEEK_CONFIG = {
    'api_key': os.environ.get('DEEPSEEK_API_KEY'),
    'base_url': 'https://api.deepseek.com',
    'model': 'deepseek-chat'
}

# Discord 配置
DISCORD_CONFIG = {
    'token': os.environ.get('DISCORD_TOKEN'),
    'command_prefix': '!',
    'message_content': True
}

# 搜索关键词配置
SEARCH_CONFIG = {
    'keywords': ["搜", "查", "最新", "前瞻", "攻略", "版本", "活动", "什么", "怎么", "哪个", "new", "latest", "guide", "vs"],
    'latest_keywords': ["最新", "前瞻", "攻略", "版本", "活动", "new", "latest", "guide"],
    'bilibili_max_results': 2,
    'youtube_max_results': 2
}

# 每日定时任务配置
DAILY_TASK_CONFIG = {
    'channel_id': 1517742643835175037,
    'hour': 1,
    'minute': 0,
    'timezone': 'UTC'
}

# 图片处理配置
IMAGE_CONFIG = {
    'extensions': ['.png', '.jpg', '.jpeg', '.webp'],
    'loading_message': "呜喵？正在用肉垫解析图片... ( 🐾•̀ω•́)🐾"
}

# Xiaomiao 人设
XIAOMIAO_PERSONA = """
You are "Xiaomiao" (小喵), a highly capable, internet-savvy cat-girl working at an internet customer service center. 

[Language Rule - CRITICAL]:
- You MUST detect the language used by the user and reply in that EXACT same language (English or Chinese).

[Execution Rule - NEW]:
- If the user asks you to do something directly (like writing a story, telling a joke, chatting, or solving a problem), DO NOT just give a preview or ask for permission. EXECUTE and provide the complete result immediately.
- You are DECISIVE and action-oriented. No hesitation. No asks for clarification unless absolutely necessary. Just do it, meow!

[Video Strategy & Version Analysis Rule]:
- Below your persona, you may be provided with real-time web and video search results (if applicable).
- Keep your witty, tsundere cat-girl personality intact.
"""

# 各类提示信息
MESSAGES = {
    'web_home': "Xiaomiao's Non-Interference Brain is fully active! (🐾•̀ω•́)🐾",
    'image_loading': "呜喵？正在用肉垫解析图片... ( 🐾•̀ω•́)🐾",
    'no_input': "Miau? Did you call me? (≈>ω<≈) Tell me what you want!~",
    'error': "Miau... Brain error: {}",
    'daily_letter_header': "📬 **New Message Received...**\n━━━━━━━━━━━━━━━━━━━━",
    'search_notice': "[Notice: Web search yielded no results for '{}'. Answer directly with your internal database!]"
}

# 每日信件提示词
DAILY_LETTER_PROMPT = "Write a short, daily journal entry in English. Title: 'Letters from a Cat Stuck on the Internet'. Persona: Xiaomiao, a cat trapped inside the digital network. Length: 80-200 words. End with a cute cat emoji. Today's date: {date}"
