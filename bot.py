import os
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from config import get_config, load_config_from_channel
from handlers import (
    start, handle_menu_buttons, handle_text_input, handle_callback,
    handle_group_message, handle_document, WAITING_CODE, WAITING_TAG_AND_HOURS,
    WAITING_BAN_USER_ID, WAITING_UNBAN, WAITING_RESET_PENALTIES
)
from database import get_inactive_users, update_activity
from utils import send_inactive_warning

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# ---------- Фоновая задача: трекер бездействия ----------
async def inactivity_checker(context):
    """Проверяет неактивных пользователей и отправляет предупреждение."""
    result = get_inactive_users()
    if "inactive" in result:
        bot = context.bot
        for uid in result["inactive"]:
            try:
                await send_inactive_warning(bot, uid)
            except Exception as e:
                logging.error(f"Не удалось отправить предупреждение {uid}: {e}")

# ---------- Основная функция ----------
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Загружаем конфиг при старте
    load_config_from_channel(application.bot)

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))

    # Обработчик главного меню (ReplyKeyboard)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handle_menu_buttons
    ))

    # Обработчик текстового ввода (состояния)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handle_text_input
    ))

    # Инлайн-кнопки
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Сообщения в группе (ИИ)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
        handle_group_message
    ))

    # Загрузка документов (компромат)
    application.add_handler(MessageHandler(
        filters.Document.ALL & filters.ChatType.PRIVATE,
        handle_document
    ))

    # --- Фоновая задача ---
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(inactivity_checker, interval=86400, first=10)

    logging.info("Бот запущен в режиме polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()