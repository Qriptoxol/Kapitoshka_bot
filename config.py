import os
import json
import logging
import requests
from datetime import datetime
from database import get_setting, set_setting

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
STORAGE_CHANNEL_ID = int(os.environ.get("STORAGE_CHANNEL_ID", 0))
CONFIG_FILE_ID_KEY = "config_file_id"

# Админы из переменной окружения (через запятую)
ADMINS_ENV = os.environ.get("BOT_ADMINS", "6890406250")
DEFAULT_ADMINS = [int(x.strip()) for x in ADMINS_ENV.split(",") if x.strip().isdigit()]

DEFAULT_CONFIG = {
    "admins": DEFAULT_ADMINS,
    "forward_limit": 5,
    "forward_period_hours": 24,
    "text_threshold": 0.7,
    "penalty_limit": 2,
    "inactivity_days": 3,
    "lockdown": False,
    "main_channel_link": "https://t.me/your_main_channel"
}

_config_cache = None
_config_last_update = None
CACHE_TTL = 300

def load_config_from_channel(bot):
    global _config_cache, _config_last_update
    file_id = get_setting(CONFIG_FILE_ID_KEY)
    if file_id:
        try:
            file = bot.get_file(file_id)
            url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
            resp = requests.get(url)
            if resp.status_code == 200:
                config = json.loads(resp.text)
                _config_cache = config
                _config_last_update = datetime.now()
                logger.info("✅ Конфиг загружен из канала.")
                return config
        except Exception as e:
            logger.error(f"Ошибка загрузки конфига: {e}")

    # Создаём новый
    logger.warning("⚠️ Конфиг не найден. Создаю новый и отправляю в канал.")
    config = DEFAULT_CONFIG.copy()
    sent = bot.send_document(
        chat_id=STORAGE_CHANNEL_ID,
        document=json.dumps(config, indent=2).encode('utf-8'),
        filename="config.json",
        caption="Конфиг бота (автосозданный)"
    )
    file_id = sent.document.file_id
    set_setting(CONFIG_FILE_ID_KEY, file_id)
    _config_cache = config
    _config_last_update = datetime.now()
    logger.info("✅ Конфиг сохранён в канале и file_id записан в БД.")
    return config

def get_config(bot=None, force_reload=False):
    global _config_cache, _config_last_update
    if force_reload or _config_cache is None or (
        datetime.now() - _config_last_update).total_seconds() > CACHE_TTL:
        if bot:
            return load_config_from_channel(bot)
        else:
            return _config_cache or DEFAULT_CONFIG
    return _config_cache

def is_admin(user_id, bot=None):
    config = get_config(bot)
    return user_id in config.get("admins", [])
