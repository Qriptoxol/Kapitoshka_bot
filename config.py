import os
import json
import requests
from datetime import datetime
from database import get_setting, set_setting

BOT_TOKEN = os.environ.get("BOT_TOKEN")
STORAGE_CHANNEL_ID = int(os.environ.get("STORAGE_CHANNEL_ID", 0))
CONFIG_FILE_ID_KEY = "config_file_id"

DEFAULT_CONFIG = {
    "admins": [6890406250],  # заполни своими ID
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
CACHE_TTL = 300  # 5 минут

def load_config_from_channel(bot):
    """Загружает конфиг из канала-хранилища или создаёт дефолтный."""
    global _config_cache, _config_last_update

    file_id = get_setting(CONFIG_FILE_ID_KEY)
    if file_id:
        try:
            file = bot.get_file(file_id)
            file_path = file.file_path
            url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
            resp = requests.get(url)
            if resp.status_code == 200:
                config = json.loads(resp.text)
                _config_cache = config
                _config_last_update = datetime.now()
                return config
        except Exception as e:
            print(f"Ошибка загрузки конфига: {e}")

    # Если файла нет или ошибка — создаём дефолтный и отправляем в канал
    return save_default_config(bot)

def save_default_config(bot):
    """Создаёт дефолтный конфиг, отправляет в канал и сохраняет file_id."""
    global _config_cache, _config_last_update

    config = DEFAULT_CONFIG.copy()
    # Отправляем как документ в канал-хранилище
    sent = bot.send_document(
        chat_id=STORAGE_CHANNEL_ID,
        document=json.dumps(config, indent=2).encode('utf-8'),
        filename="config.json",
        caption="Дефолтный конфиг (не удалять)"
    )
    file_id = sent.document.file_id
    # Сохраняем file_id в БД
    set_setting(CONFIG_FILE_ID_KEY, file_id)
    _config_cache = config
    _config_last_update = datetime.now()
    return config

def get_config(bot=None, force_reload=False):
    """Возвращает актуальный конфиг с кешированием."""
    global _config_cache, _config_last_update
    if force_reload or _config_cache is None or (
        datetime.now() - _config_last_update).total_seconds() > CACHE_TTL:
        if bot:
            return load_config_from_channel(bot)
        else:
            # Если бот не передан, возвращаем последний кеш или дефолт
            return _config_cache or DEFAULT_CONFIG
    return _config_cache

def is_admin(user_id, bot=None):
    return user_id in get_config(bot).get("admins", [])