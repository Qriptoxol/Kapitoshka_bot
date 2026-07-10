import os
import logging
import threading
import time
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, filters
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
            time.sleep(86400)  # 24 часа
            inactivity_checker(bot)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()

def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    bot = updater.bot

    # Загружаем конфиг при старте
    load_config_from_channel(bot)

    # Регистрируем обработчики
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("reload_config", reload_config))

    dp.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.PRIVATE,
        handle_menu_buttons
    ))
    dp.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.PRIVATE,
        handle_text_input
    ))
    dp.add_handler(CallbackQueryHandler(handle_callback))

    dp.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & (filters.GROUP | filters.SUPERGROUP),
        handle_group_message
    ))
    dp.add_handler(MessageHandler(
        filters.DOCUMENT & filters.PRIVATE,
        handle_document
    ))

    # Запускаем фоновый поток для трекера бездействия
    start_inactivity_thread(bot)

    logger.info("Бот запущен в режиме polling...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
