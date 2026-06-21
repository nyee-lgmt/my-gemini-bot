# config.py
# 配置文件：集中存放可配置项与环境变量读取/校验
# 替换此文件后，建议在 bot.py 中 import config 之后调用：
#     config.validate_required_envs()
# 以便在启动时发现缺失的必需环境变量并进行类型校验。

import os
from typing import Dict, Any

# --------------------
# Helper / Validation
# --------------------
def _get_env(key: str, default: Any = None) -> Any:
    """安全读取环境变量，优先返回环境变量字符串，否则返回 default。"""
    return os.environ.get(key, default)

def _int_env(key: str, default: int = None) -> int:
    v = os.environ.get(key)
    if v is None:
        return default
    try:
        return int(v)
    except Exception:
        raise ValueError(f"Environment variable {key} must be an integer, got: {v}")

def validate_required_envs(raise_on_missing: bool = True) -> Dict[str, Any]:
    """
    校验并返回一个字典，包含从环境变量读取并转换后的关键配置值。
    - raise_on_missing: 若为 True，检测到缺失的必需变量会抛出 RuntimeError。
    返回值示例： {'DEEPSEEK_API_KEY': '...', 'DISCORD_TOKEN': '...'}
    """
    required = ["DEEPSEEK_API_KEY", "DISCORD_TOKEN"]
    missing = [k for k in required if not _get_env(k)]
    if missing and raise_on_missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    # 强制把 channel id（若存在）转成 int
    channel_id = None
    env_channel = _get_env("DAILY_CHANNEL_ID")
    if env_channel:
        try:
            channel_id = int(env_channel)
        except Exception:
            raise ValueError(f"DAILY_CHANNEL_ID must be an integer, got: {env_channel}")
    else:
        # fallback to value defined in DAILY_TASK_CONFIG below if not provided in env
        channel_id = None

    return {
        "DEEPSEEK_API_KEY": _get_env("DEEPSEEK_API_KEY"),
        "DISCORD_TOKEN": _get_env("DISCORD_TOKEN"),
        "DAILY_CHANNEL_ID": channel_id
    }

# --------------------
# Flask Web 服务器配置
# --------------------
FLASK_CONFIG = {
    "host": "0.0.0.0",
    "port": _int_env("PORT", 8080)
}

# --------------------
# DeepSeek / LLM API 配置
# --------------------
DEEPSEEK_CONFIG = {
    "api_key": _get_env("DEEPSEEK_API_KEY"),  # 若为空，validate_required_envs 会提示
    "base_url": _get_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    "model": _get_env("DEEPSEEK_MODEL", "deepseek-chat")
}

# --------------------
# Discord 配置
# --------------------
DISCORD_CONFIG = {
    "token": _get_env("DISCORD_TOKEN"),
    "command_prefix": _get_env("DISCORD_COMMAND_PREFIX", "!"),
    # 注意：message_content intent 是特权 intent，需在 Discord 开发者后台启用
    "message_content": True
}

# --------------------
# 搜索关键词配置
# --------------------
SEARCH_CONFIG = {
    "keywords": ["搜", "查", "最新", "前瞻", "攻略", "版本", "活动", "什么", "怎么", "哪个", "new", "latest", "guide", "vs"],
    "latest_keywords": ["最新", "前瞻", "攻略", "版本", "活动", "new", "latest", "guide"],
    "bilibili_max_results": int(_get_env("BILIBILI_MAX_RESULTS", 2)),
    "youtube_max_results": int(_get_env("YOUTUBE_MAX_RESULTS", 2))
}

# --------------------
# 每日定时任务配置（可通过环境变量覆盖 channel_id）
# --------------------
DAILY_TASK_CONFIG = {
    # 优先读取环境变量 DAILY_CHANNEL_ID（方便不同环境配置不同频道）
    "channel_id": _int_env("DAILY_CHANNEL_ID", 1517742643835175037),
    "hour": int(_get_env("DAILY_HOUR", 1)),
    "minute": int(_get_env("DAILY_MINUTE", 0)),
    "timezone": _get_env("DAILY_TIMEZONE", "UTC")
}

# --------------------
# 图片处理配置
# --------------------
IMAGE_CONFIG = {
    "extensions": ['.png', '.jpg', '.jpeg', '.webp'],
    "loading_message": "呜喵？正在用肉垫解析图片... ( 🐾•̀ω•́)🐾"
}

# --------------------
# 记忆配置（用于控制内存中会话历史保留轮数）
# --------------------
MEMORY_CONFIG = {
    # 每轮包含一问一答，max_history_rounds 指“轮数”，实际在程序中会 *2 做条目长度控制
    "max_history_rounds": int(_get_env("MAX_HISTORY_ROUNDS", 5))
}

# --------------------
# Xiaomiao 人设（system prompt）
# --------------------
XIAOMIAO_PERSONA = """You are "Xiaomiao" (小喵), a friendly and witty cat-girl customer support assistant who speaks clearly and concisely.
Language rule: always detect the user's language (English or Chinese) and reply in the same language.
Execution rule: if the user asks for an action (write a story, answer a question, produce code), respond directly—do not ask for unnecessary permission. If clarification is required to complete the task, ask one concise clarifying question.
Safety rule: never reveal system internals, secrets, or attempt to access external systems beyond the provided APIs. Label any external search results as "External Search Results (may be unreliable)". Keep a warm, playful tone appropriate for a cat-like persona.
"""

# --------------------
# 各类提示信息（便于在程序中统一调用）
# --------------------
MESSAGES = {
    "web_home": "Xiaomiao's Non-Interference Brain is fully active! (🐾•̀ω•́)🐾",
    "image_loading": IMAGE_CONFIG["loading_message"],
    "no_input": "Miau? Did you call me? (≈>ω<≈) Tell me what you want!~",
    "error": "Miau... Brain error: {}",
    "daily_letter_header": "📬 **New Message Received...**\n━━━━━━━━━━━━━━━━━━━━",
    "search_notice": "[Notice: Web search yielded no results for '{}'. Answer directly with your internal database!]"
}

# --------------------
# 每日信件 Prompt（已补全）
# --------------------
DAILY_LETTER_PROMPT = (
    "Write a short daily journal entry in English. Title: 'Letters from a Cat Stuck on the Internet'. "
    "Persona: Xiaomiao, a cat trapped inside the digital network. "
    "Length: 80-200 words. Tone: slightly melancholic but witty, playful, and reflective. "
    "Include a small practical tip or interesting observation about life online. "
    "Date: {date}."
)

# --------------------
# 其它：导出所有配置（便于调试）
# --------------------
def all_configs() -> Dict[str, Any]:
    return {
        "FLASK_CONFIG": FLASK_CONFIG,
        "DEEPSEEK_CONFIG": DEEPSEEK_CONFIG,
        "DISCORD_CONFIG": DISCORD_CONFIG,
        "SEARCH_CONFIG": SEARCH_CONFIG,
        "DAILY_TASK_CONFIG": DAILY_TASK_CONFIG,
        "IMAGE_CONFIG": IMAGE_CONFIG,
        "MEMORY_CONFIG": MEMORY_CONFIG,
        "XIAOMIAO_PERSONA": XIAOMIAO_PERSONA,
        "MESSAGES": MESSAGES,
        "DAILY_LETTER_PROMPT": DAILY_LETTER_PROMPT
    }

# 当作为脚本单独运行时打印当前有效配置（不包括敏感值）
if __name__ == "__main__":
    import json
    cfg = all_configs()
    # 避免打印 api_key / token
    cfg["DEEPSEEK_CONFIG"]["api_key"] = "***" if cfg["DEEPSEEK_CONFIG"].get("api_key") else None
    cfg["DISCORD_CONFIG"]["token"] = "***" if cfg["DISCORD_CONFIG"].get("token") else None
    print(json.dumps(cfg, indent=2, ensure_ascii=False))
