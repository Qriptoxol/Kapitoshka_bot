import os
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from config import load_config_from_channel
from handlers import (
    start, handle_menu_buttons, handle_text_input, handle_callback,
    handle_group_message, handle_document
)
from database import get_inactive_users
from utils import send_inactive_warning

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.environ.get("BOT_TOKEN")

async def inactivity_checker(application):
    """Фоновая задача: проверка бездействия каждые 24 часа."""
    while True:
        await asyncio.sleep(86400)  # 24 часа
        try:
            result = get_inactive_users()
            if "inactive" in result:
                bot = application.bot
                for uid in result["inactive"]:
                    try:
                        await send_inactive_warning(bot, uid)
                    except Exception as e:
                        logging.error(f"Не удалось отправить предупреждение {uid}: {e}")
        except Exception as e:
            logging.error(f"Ошибка в трекере бездействия: {e}")

async def init_app():
    """Асинхронная инициализация приложения и загрузка конфига."""
    application = Application.builder().token(BOT_TOKEN).build()
    await load_config_from_channel(application.bot)
    return application

def main():
    # Инициализация приложения с загрузкой конфига
    application = asyncio.run(init_app())

    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handle_menu_buttons
    ))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handle_text_input
    ))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
        handle_group_message
    ))
    application.add_handler(MessageHandler(
        filters.Document.ALL & filters.ChatType.PRIVATE,
        handle_document
    ))

    # Запускаем фоновую задачу для трекера бездействия (без JobQueue)
    loop = asyncio.get_event_loop()
    loop.create_task(inactivity_checker(application))

    logging.info("Бот запущен в режиме polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
