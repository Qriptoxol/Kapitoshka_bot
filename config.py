import os
import json
import asyncio
import aiohttp
import logging
from datetime import datetime
from database import get_setting, set_setting

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
STORAGE_CHANNEL_ID = int(os.environ.get("STORAGE_CHANNEL_ID", 0))
CONFIG_FILE_ID_KEY = "config_file_id"

# Админы из переменной окружения (через запятую)
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

async def aget_setting(key):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_setting, key)

async def aset_setting(key, value):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, set_setting, key, value)

async def load_config_from_channel(bot):
    global _config_cache, _config_last_update

    file_id = await aget_setting(CONFIG_FILE_ID_KEY)
    logger.info(f"Загружаем file_id из БД: {file_id}")

    if file_id:
        try:
            file = await bot.get_file(file_id)
            url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        config = json.loads(text)
                        _config_cache = config
                        _config_last_update = datetime.now()
                        logger.info("✅ Конфиг успешно загружен из канала.")
                        return config
                    else:
                        logger.error(f"Не удалось скачать конфиг: {resp.status}")
        except Exception as e:
            logger.error(f"Ошибка загрузки конфига: {e}")

    # Если не загрузился – создаём новый
    logger.warning("⚠️ Конфиг не найден. Создаю новый и отправляю в канал.")
    config = DEFAULT_CONFIG.copy()
    sent = await bot.send_document(
        chat_id=STORAGE_CHANNEL_ID,
        document=json.dumps(config, indent=2).encode('utf-8'),
        filename="config.json",
        caption="Конфиг бота (автосозданный)"
    )
    file_id = sent.document.file_id
    logger.info(f"✅ Конфиг сохранён в канале с file_id: {file_id}")
    await aset_setting(CONFIG_FILE_ID_KEY, file_id)
    logger.info("✅ file_id сохранён в БД.")

    _config_cache = config
    _config_last_update = datetime.now()
    return config

async def get_config(bot=None, force_reload=False):
    global _config_cache, _config_last_update
    if force_reload or _config_cache is None or (
        datetime.now() - _config_last_update).total_seconds() > CACHE_TTL:
        if bot:
            return await load_config_from_channel(bot)
        else:
            return _config_cache or DEFAULT_CONFIG
    return _config_cache

async def is_admin(user_id, bot=None):
    config = await get_config(bot)
    return user_id in config.get("admins", [])
