import os
import json
import asyncio
import aiohttp
from datetime import datetime
from database import get_setting, set_setting

BOT_TOKEN = os.environ.get("BOT_TOKEN")
STORAGE_CHANNEL_ID = int(os.environ.get("STORAGE_CHANNEL_ID", 0))
CONFIG_FILE_ID_KEY = "config_file_id"

# Получаем админов из переменной окружения (через запятую)
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

async def aget_setting(key):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_setting, key)

async def aset_setting(key, value):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, set_setting, key, value)

async def load_config_from_channel(bot):
    global _config_cache, _config_last_update

    file_id = await aget_setting(CONFIG_FILE_ID_KEY)
    if file_id:
        try:
            file = await bot.get_file(file_id)
            file_path = file.file_path
            url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        config = json.loads(text)
                        _config_cache = config
                        _config_last_update = datetime.now()
                        return config
        except Exception as e:
            print(f"Ошибка загрузки конфига: {e}")

    # Если файла нет – создаём новый конфиг и отправляем в канал
    print("⚠️ Конфиг не найден. Создаю новый и отправляю в канал.")
    config = DEFAULT_CONFIG.copy()
    # Отправляем в канал
    try:
        sent = await bot.send_document(
            chat_id=STORAGE_CHANNEL_ID,
            document=json.dumps(config, indent=2).encode('utf-8'),
            filename="config.json",
            caption="Конфиг бота (автосозданный)"
        )
        file_id = sent.document.file_id
        await aset_setting(CONFIG_FILE_ID_KEY, file_id)
        print(f"✅ Конфиг сохранён в канале с file_id: {file_id}")
    except Exception as e:
        print(f"❌ Не удалось отправить конфиг в канал: {e}")
        # Продолжаем с дефолтным конфигом в памяти
    _config_cache = config
    _config_last_update = datetime.now()
    return _config_cache

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
