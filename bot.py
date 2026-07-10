import os
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from config import load_config_from_channel, get_config
from handlers import (
    start, handle_menu_buttons, handle_text_input, handle_callback,
    handle_group_message, handle_document
)
from database import get_inactive_users
from utils import send_inactive_warning

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.environ.get("BOT_TOKEN")

async def inactivity_checker(context):
    """Проверяет неактивных пользователей и отправляет предупреждение."""
    result = get_inactive_users()  # синхронная функция, можно оставить
    if "inactive" in result:
        bot = context.bot
        for uid in result["inactive"]:
            try:
                await send_inactive_warning(bot, uid)
            except Exception as e:
                logging.error(f"Не удалось отправить предупреждение {uid}: {e}")

async def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Загружаем конфиг при старте (асинхронно)
    await load_config_from_channel(application.bot)

    # Регистрируем обработчики
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

    # Фоновая задача – трекер бездействия (раз в 24 часа)
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(inactivity_checker, interval=86400, first=10)

    logging.info("Бот запущен в режиме polling...")
    await application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    asyncio.run(main())
