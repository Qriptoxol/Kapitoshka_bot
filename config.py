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

ADMINS_ENV = os.environ.get("BOT_ADMINS", "")
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
    logger.info(f"📥 Получен file_id из БД: {file_id}")

    if file_id:
        try:
            file = bot.get_file(file_id)
            url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
            logger.info(f"📥 Скачиваю конфиг по URL: {url}")
            resp = requests.get(url)
            if resp.status_code == 200:
                config = json.loads(resp.text)
                _config_cache = config
                _config_last_update = datetime.now()
                logger.info("✅ Конфиг загружен из канала.")
                return config
            else:
                logger.error(f"❌ Ошибка скачивания: {resp.status_code}")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки конфига: {e}")
    else:
        logger.warning("⚠️ file_id отсутствует в БД.")

    # Если не загрузился — создаём новый
    logger.warning("⚠️ Конфиг не найден. Создаю новый и отправляю в канал.")
    config = DEFAULT_CONFIG.copy()
    try:
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
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке конфига в канал: {e}")
        # Даже если не отправилось, используем конфиг в памяти
        _config_cache = config
        _config_last_update = datetime.now()
    return _config_cache

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
