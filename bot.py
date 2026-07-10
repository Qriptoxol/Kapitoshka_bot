import os
import sys
import subprocess
import importlib

# === АВТОУСТАНОВКА НУЖНОЙ ВЕРСИИ ===
def ensure_telegram_version():
    try:
        import telegram
        version = telegram.__version__
        if version.startswith('13.'):
            return
        else:
            print(f"⚠️ Версия {version} не подходит. Переустанавливаю...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'python-telegram-bot==13.7'])
            print("✅ Установлена версия 13.7. Перезапустите бота.")
            sys.exit(0)
    except ImportError:
        print("⚠️ Библиотека не найдена. Устанавливаю...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'python-telegram-bot==13.7'])
        print("✅ Установлена версия 13.7. Перезапустите бота.")
        sys.exit(0)

ensure_telegram_version()
import logging
import threading
import time
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
from config import load_config_from_channel
from handlers import (
    start, reload_config, handle_menu_buttons, handle_text_input,
    handle_callback, handle_group_message, handle_document
)
from analytics import inactivity_checker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
BOT_TOKEN = os.environ.get("BOT_TOKEN")

def start_inactivity_thread(bot):
    def run():
        while True:
            time.sleep(86400)
            inactivity_checker(bot)
    threading.Thread(target=run, daemon=True).start()

def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    bot = updater.bot

    # загружаем конфиг при старте
    load_config_from_channel(bot)

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("reload_config", reload_config))

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.private, handle_menu_buttons))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.private, handle_text_input))
    dp.add_handler(CallbackQueryHandler(handle_callback))
    # Для групп используем только Filters.group (он охватывает и супергруппы)
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.group, handle_group_message))
    dp.add_handler(MessageHandler(Filters.document & Filters.private, handle_document))

    start_inactivity_thread(bot)
    logger.info("Бот запущен в режиме polling...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
