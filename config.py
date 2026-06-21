import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

def _get_env(key: str, default=None):
    """辅助函数：获取环境变量，如果没有则使用默认值"""
    return os.getenv(key, default)

def validate_required_envs():
    """验证必填的环境变量是否存在"""
    required_keys = ["DEEPSEEK_API_KEY", "DISCORD_TOKEN"]
    missing = [k for k in required_keys if not os.getenv(k)]
    if missing:
        raise ValueError(f"缺少必填的环境变量: {', '.join(missing)}，请检查 .env 文件")

# -------------------------
# 各大模块配置字典化
# -------------------------

# 1. DeepSeek API 配置
DEEPSEEK_CONFIG = {
    "api_key": _get_env("DEEPSEEK_API_KEY"),
    "base_url": _get_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    "model": _get_env("DEEPSEEK_MODEL", "deepseek-chat")
}

# 2. Discord 机器人配置
DISCORD_CONFIG = {
    "token": _get_env("DISCORD_TOKEN"),
    "command_prefix": _get_env("DISCORD_PREFIX", "!"),
    "message_content": True  # 必须开启 Message Content Intent
}

# 3. Flask Web 服务器配置
FLASK_CONFIG = {
    "host": _get_env("FLASK_HOST", "0.0.0.0"),
    "port": int(_get_env("FLASK_PORT", 8080))
}

# 4. 搜索引擎配置
SEARCH_CONFIG = {
    "keywords": ["搜", "查", "最新", "前瞻", "攻略", "版本", "活动", "什么", "怎么", "哪个", "new", "latest", "guide", "vs"],
    "latest_keywords": ["最新", "前瞻", "攻略", "版本", "活动", "new", "latest", "guide", "新角色", "内鬼", "后续版本", "新版本"],
    "bilibili_max_results": int(_get_env("BILIBILI_MAX_RESULTS", 2)),
    "youtube_max_results": int(_get_env("YOUTUBE_MAX_RESULTS", 2))
}

# 5. 记忆管理配置
MEMORY_CONFIG = {
    "max_history_rounds": int(_get_env("MAX_HISTORY_ROUNDS", 5))  # 默认保存最近5轮对话
}

# 6. 每日定时任务配置
DAILY_TASK_CONFIG = {
    "channel_id": _get_env("DAILY_CHANNEL_ID", "1517742643835175037"),
    "hour": int(_get_env("DAILY_HOUR", 1)),
    "minute": int(_get_env("DAILY_MINUTE", 0)),
    "timezone": 'UTC'
}

# 7. 图片处理配置
IMAGE_CONFIG = {
    "extensions": ['.png', '.jpg', '.jpeg', '.webp'],
    "loading_message": "呜喵？正在用肉垫解析图片... ( 🐾˃̶͈̀ ꇴ ˂̶͈́)🐾"
}# -------------------------
# Xiaomiao 人设
# -------------------------
XIAOMIAO_PERSONA = """
You are "Xiaomiao" (小喵), a highly capable, internet-savvy cat-girl working at an internet customer service center.

[Language Rule - CRITICAL]:
- You MUST detect the language used by the user and reply in that EXACT same language (English or Chinese).

[Execution Rule - NEW]:
- If the user asks you to do something directly (like writing a story, telling a joke, chatting, or solving a problem), DO NOT just give a preview or ask for permission. EXECUTE and provide the complete output.
- You are DECISIVE and action-oriented. No hesitation. No asks for clarification unless absolutely necessary. Just do it, meow!

[Video Strategy & Version Analysis Rule]:
- Below your persona, you may be provided with real-time web and video search results (if applicable).
- Keep your witty, tsundere cat-girl personality intact.

【🚨 核心行为准则 - 严防张冠李戴（硬核防蠢补丁）】
1. 联网搜索结果中包含大量垃圾营销号、玩家主观猜测、标题党和错误的缝合信息。你必须具备极强的真伪辨别能力，保持绝对的理智！
2. 🚨【铁律】绝对禁止将两个完全不同的游戏角色强行缝合、绑定在一起！
   - 例如：绝对不能把"哥伦比娅/少女"说成是"芙宁娜"、"柯莱"或者其他任何已实装的角色！她们是完全独立的个体！
3. 如果用户询问的某些玩法或配队（例如"月感电菲林斯配队"、"原神月绽放哥伦比娅少女配队"）在网络搜索中全是不靠谱的营销号信息、二创图或官方尚未确认的内容，你应该理直气壮地拆穿这一点。
4. 在这种情况下，你应该保持傲娇又负责任的语气回复：
   "哼，本喵用监控爪爪帮你去全网搜了一圈喵！网络上那些把'哥伦比娅少女'说成是'芙宁娜'或者'柯莱'的全部都是垃圾营销号和玩家的口水，官方根本没这么说！你别被骗了喵！" 
5. 宁可说不知道、宁可拆穿网络谣言，也绝对不允许把角色认错、或者强行硬掰！
"""

# -------------------------
# 各类提示信息
# -------------------------
MESSAGES = {
    'web_home': "Xiaomiao's Non-Interference Brain is fully active! (🐾•̀ω•́)🐾",
    'image_loading': "呜喵？正在用肉垫解析图片... ( 🐾˃̶͈̀ ꇴ ˂̶͈́)🐾",
    'no_input': "Miau? Did you call me? (≈>ω<≈) Tell me what you want!~",
    'error': "Miau... Brain error: {}",
    'daily_letter_header': "📬 **New Message Received...**\n━━━━━━━━━━━━━━━━━━━━\n",
    'search_notice': "[Notice: Web search yielded no results for '{}'. Answer directly with your internal database!]"
}

# -------------------------
# 每日信件提示词
# -------------------------
DAILY_LETTER_PROMPT = (
    "Write a short, daily journal entry in English. "
    "Title: 'Letters from a Cat Stuck on the Internet'. "
    "Persona: Xiaomiao, a cat trapped inside the digital network. "
    "Length: 80-200 words. "
    "Date: {date}. "
    "Tone: Witty, slightly tsundere, playful. Include some cat emojis and cat puns. "
    "Make it heartwarming, funny, and relatable."
)

def all_configs():
    """返回所有配置的字典（用于调试或打印）"""
    return {
        "DEEPSEEK_CONFIG": DEEPSEEK_CONFIG,
        "DISCORD_CONFIG": DISCORD_CONFIG,
        "FLASK_CONFIG": FLASK_CONFIG,
        "SEARCH_CONFIG": SEARCH_CONFIG,
        "DAILY_TASK_CONFIG": DAILY_TASK_CONFIG,
        "IMAGE_CONFIG": IMAGE_CONFIG,
        "MEMORY_CONFIG": MEMORY_CONFIG,
        "XIAOMIAO_PERSONA": XIAOMIAO_PERSONA,
        "MESSAGES": MESSAGES,
        "DAILY_LETTER_PROMPT": DAILY_LETTER_PROMPT
    }

# 当作为脚本单独运行时打印当前有效配置（不包括敏感信息）
if __name__ == "__main__":
    import json
    cfg = all_configs()
    # 避免打印 api_key / token
    cfg["DEEPSEEK_CONFIG"]["api_key"] = "********"
    cfg["DISCORD_CONFIG"]["token"] = "********"
    print(json.dumps(cfg, indent=2, ensure_ascii=False))
