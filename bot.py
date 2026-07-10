import os
import json
import asyncio
import requests
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

# ========== ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ==========
BOT_TOKEN = "8944304831:AAGiZhHGK-DHD8e5GTiM23wQbXE7s_bnLIA"
SUPABASE_URL = "https://liboxekacquvznqyxxzp.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxpYm94ZWthY3F1dnpucXl4eHpwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODM2Mjg1OTAsImV4cCI6MjA5OTIwNDU5MH0.0oglCN9qNC1vWXX36Y40a1DW089o-C_6jB28bMuB1XY"
STORAGE_CHANNEL_ID = -1004426342852 # например, -1001234567890
CONFIG_FILE_ID = os.environ.get("CONFIG_FILE_ID")  # опционально, для чтения конфига из канала

EDGE_FUNCTION_URL = f"{SUPABASE_URL}/functions/v1/main"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
}

# Состояния для ConversationHandler
WAITING_CODE = 1
WAITING_TAG_AND_HOURS = 2
WAITING_BAN_USER_ID = 3
WAITING_RESET_PENALTIES = 4
WAITING_UNBAN = 5

# Глобальный кеш конфига
CONFIG = None
CONFIG_LAST_UPDATE = None
CONFIG_CACHE_TTL = 300

# ========== РАБОТА С КОНФИГОМ ==========
def get_default_config():
    return {
        "admins": [6890406250],  # сюда впиши свои ID
        "forward_limit": 5,
        "forward_period_hours": 24,
        "text_threshold": 0.7,
        "penalty_limit": 2,
        "inactivity_days": 3,
        "lockdown": False
    }

def load_config_from_telegram(bot):
    global CONFIG, CONFIG_LAST_UPDATE
    if not CONFIG_FILE_ID:
        CONFIG = get_default_config()
        CONFIG_LAST_UPDATE = datetime.now()
        return CONFIG
    try:
        file_path = bot.get_file(CONFIG_FILE_ID).file_path
        # Скачиваем содержимое (можно через requests)
        url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        resp = requests.get(url)
        if resp.status_code == 200:
            config = json.loads(resp.text)
            CONFIG = config
            CONFIG_LAST_UPDATE = datetime.now()
            return config
    except Exception as e:
        print(f"Ошибка загрузки конфига: {e}")
    return get_default_config()

def get_config(bot=None):
    global CONFIG, CONFIG_LAST_UPDATE
    if CONFIG is None or (datetime.now() - CONFIG_LAST_UPDATE).total_seconds() > CONFIG_CACHE_TTL:
        if bot:
            return load_config_from_telegram(bot)
        else:
            return get_default_config()
    return CONFIG

def is_admin(user_id, bot=None):
    return user_id in get_config(bot).get("admins", [])

# ========== ВЫЗОВ SUPABASE EDGE FUNCTION ==========
def call_supabase(action, params):
    payload = {"action": action, **params}
    try:
        resp = requests.post(EDGE_FUNCTION_URL, json=payload, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text}"}
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

# ========== ОБРАБОТЧИКИ КОМАНД ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or ""

    ref_code = context.args[0] if context.args else None
    result = call_supabase("register", {
        "user_id": user_id,
        "username": username,
        "referrer_code": ref_code
    })
    if "error" in result:
        await update.message.reply_text("Ошибка регистрации, попробуйте позже.")
        return

    keyboard = [
        ["📎 Моя реф. ссылка", "🔑 Активировать код"],
    ]
    if is_admin(user_id, context.bot):
        keyboard.append(["⚙️ Админ-панель"])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        f"👋 Привет, {username}! Ты зарегистрирован. Выбери действие:",
        reply_markup=reply_markup
    )

async def reload_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, context.bot):
        await update.message.reply_text("Доступ запрещён.")
        return
    load_config_from_telegram(context.bot)
    await update.message.reply_text("Конфиг перезагружен.")

# ========== ОБРАБОТЧИКИ КНОПОК (ReplyKeyboard) ==========
async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "📎 Моя реф. ссылка":
        result = call_supabase("referral", {"user_id": user_id})
        if "code" in result:
            bot_username = (await context.bot.get_me()).username
            ref_link = f"https://t.me/{bot_username}?start={result['code']}"
            await update.message.reply_text(f"Твоя ссылка:\n{ref_link}")
        else:
            await update.message.reply_text("Не удалось создать ссылку.")

    elif text == "🔑 Активировать код":
        await update.message.reply_text("Введи кодовое слово (промокод):")
        return WAITING_CODE

    elif text == "⚙️ Админ-панель":
        if not is_admin(user_id, context.bot):
            await update.message.reply_text("Доступ запрещён.")
            return
        keyboard = [
            ["➕ Добавить компромат", "🎫 Создать код"],
            ["📋 Список кодов", "🚫 Бан пользователя"],
            ["🔓 Разбан", "🔄 Сброс штрафов"],
            ["🔒 Lockdown", "🔓 Unlock", "📊 Логи"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Админ-панель:", reply_markup=reply_markup)

    # ---- Админ-кнопки ----
    elif text == "➕ Добавить компромат":
        if not is_admin(user_id, context.bot): return
        await update.message.reply_text("Отправь файл и в подписи укажи тег (например, #tag).")

    elif text == "🎫 Создать код":
        if not is_admin(user_id, context.bot): return
        await update.message.reply_text("Введи тег файла и срок в часах через пробел: тег 24")
        return WAITING_TAG_AND_HOURS

    elif text == "📋 Список кодов":
        if not is_admin(user_id, context.bot): return
        result = call_supabase("list_codes", {})
        if "codes" in result:
            lines = [f"{c['code']} → {c['file_tag']} (exp: {c['expires_at']})" for c in result['codes']]
            await update.message.reply_text("\n".join(lines) or "Нет активных кодов.")
        else:
            await update.message.reply_text("Ошибка получения списка.")

    elif text == "🚫 Бан пользователя":
        if not is_admin(user_id, context.bot): return
        await update.message.reply_text("Введи ID пользователя для бана:")
        return WAITING_BAN_USER_ID

    elif text == "🔓 Разбан":
        if not is_admin(user_id, context.bot): return
        await update.message.reply_text("Введи ID пользователя для разбана:")
        return WAITING_UNBAN

    elif text == "🔄 Сброс штрафов":
        if not is_admin(user_id, context.bot): return
        await update.message.reply_text("Введи ID пользователя для сброса штрафов:")
        return WAITING_RESET_PENALTIES

    elif text == "🔒 Lockdown":
        if not is_admin(user_id, context.bot): return
        call_supabase("lockdown", {"enabled": True})
        await update.message.reply_text("Режим Lockdown включён (новые входы заблокированы).")

    elif text == "🔓 Unlock":
        if not is_admin(user_id, context.bot): return
        call_supabase("lockdown", {"enabled": False})
        await update.message.reply_text("Lockdown отключён.")

    elif text == "📊 Логи":
        if not is_admin(user_id, context.bot): return
        # Можно отправить последний файл логов из канала-хранилища (реализуй при необходимости)
        await update.message.reply_text("Функция логов в разработке.")

    return ConversationHandler.END

# ========== ОБРАБОТЧИКИ ВВОДА ТЕКСТА (состояния) ==========
async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = context.user_data.get("state")

    if state == WAITING_CODE:
        result = call_supabase("activate_code", {"user_id": user_id, "code": text})
        if "error" in result:
            await update.message.reply_text(f"❌ {result['error']}")
        else:
            file_tag = result.get("file_tag")
            if file_tag:
                file_res = call_supabase("get_file", {"file_tag": file_tag})
                if "file_id" in file_res:
                    await update.message.reply_text("✅ Код активирован! Вот файл:")
                    await context.bot.send_document(chat_id=user_id, document=file_res["file_id"])
                else:
                    await update.message.reply_text("Файл не найден.")
        context.user_data.pop("state", None)

    elif state == WAITING_TAG_AND_HOURS:
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text("Введи тег и часы через пробел, например: secret 24")
            return
        tag, hours_str = parts[0], parts[1]
        try:
            hours = int(hours_str)
        except ValueError:
            await update.message.reply_text("Часы должны быть числом.")
            return
        result = call_supabase("gen_code", {"admin_id": user_id, "file_tag": tag, "hours": hours})
        if "code" in result:
            await update.message.reply_text(f"✅ Код создан: {result['code']}\nДействует до {result['expires_at']}")
        else:
            await update.message.reply_text(f"Ошибка: {result.get('error', 'неизвестная')}")
        context.user_data.pop("state", None)

    elif state == WAITING_BAN_USER_ID:
        try:
            target_id = int(text)
        except ValueError:
            await update.message.reply_text("ID должен быть числом.")
            return
        # Открываем выбор срока через инлайн-кнопки
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("1 час", callback_data=f"ban_{target_id}_1h"),
             InlineKeyboardButton("24 часа", callback_data=f"ban_{target_id}_24h")],
            [InlineKeyboardButton("7 дней", callback_data=f"ban_{target_id}_7d"),
             InlineKeyboardButton("Навсегда", callback_data=f"ban_{target_id}_forever")],
            [InlineKeyboardButton("Отмена", callback_data="ban_cancel")]
        ])
        await update.message.reply_text(f"Выбери срок бана для {target_id}:", reply_markup=keyboard)
        context.user_data.pop("state", None)

    elif state == WAITING_UNBAN:
        try:
            target_id = int(text)
        except ValueError:
            await update.message.reply_text("ID должен быть числом.")
            return
        call_supabase("unban", {"user_id": target_id})
        await update.message.reply_text(f"Пользователь {target_id} разбанен.")
        context.user_data.pop("state", None)

    elif state == WAITING_RESET_PENALTIES:
        try:
            target_id = int(text)
        except ValueError:
            await update.message.reply_text("ID должен быть числом.")
            return
        call_supabase("reset_penalties", {"user_id": target_id})
        await update.message.reply_text(f"Штрафы для {target_id} сброшены.")
        context.user_data.pop("state", None)

# ========== ОБРАБОТЧИКИ ИНЛАЙН-КНОПОК ==========
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    # ---- Подозрения (звоночки) ----
    if data.startswith("suspect_"):
        parts = data.split("_")
        suspicion_id = int(parts[1])
        action = parts[2]
        if action == "false":
            call_supabase("resolve_suspicion", {"suspicion_id": suspicion_id, "resolution": "false_positive", "admin_id": user_id})
            await query.edit_message_text("✅ Помечено как ложное срабатывание.")
        elif action == "ban":
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("1 час", callback_data=f"ban_suspect_{suspicion_id}_1h"),
                 InlineKeyboardButton("24 часа", callback_data=f"ban_suspect_{suspicion_id}_24h")],
                [InlineKeyboardButton("7 дней", callback_data=f"ban_suspect_{suspicion_id}_7d"),
                 InlineKeyboardButton("Навсегда", callback_data=f"ban_suspect_{suspicion_id}_forever")],
                [InlineKeyboardButton("Отмена", callback_data="ban_cancel")]
            ])
            await query.edit_message_text("Выбери срок бана:", reply_markup=keyboard)
        elif action == "proof":
            result = call_supabase("get_suspicion_details", {"suspicion_id": suspicion_id})
            if "details" in result:
                details = result["details"]
                report = f"📄 Отчёт по подозрению #{suspicion_id}\n"
                report += f"Пользователь: {details.get('username', 'unknown')} (ID: {details.get('user_id')})\n"
                report += f"Тип: {details.get('type')}\n"
                report += f"Вес: {details.get('weight')}\n"
                report += f"Детали: {json.dumps(details.get('data', {}), indent=2, ensure_ascii=False)}"
                await query.message.reply_text(report[:4096])
            else:
                await query.message.reply_text("Не удалось загрузить пруфы.")

    # ---- Выбор срока бана для подозрения ----
    elif data.startswith("ban_suspect_"):
        parts = data.split("_")
        suspicion_id = int(parts[2])
        duration = parts[3]
        if duration == "cancel":
            await query.edit_message_text("Отменено.")
            return
        susp = call_supabase("get_suspicion", {"suspicion_id": suspicion_id})
        if "user_id" in susp:
            target_id = susp["user_id"]
            call_supabase("ban", {"admin_id": user_id, "user_id": target_id, "duration": duration})
            await query.edit_message_text(f"✅ Пользователь {target_id} забанен на {duration}.")
        else:
            await query.edit_message_text("Ошибка получения данных.")

    # ---- Бан по команде (из админ-панели) ----
    elif data.startswith("ban_"):
        parts = data.split("_")
        target_id = int(parts[1])
        duration = parts[2] if len(parts) > 2 else None
        if duration == "cancel":
            await query.edit_message_text("Отменено.")
            return
        if duration:
            call_supabase("ban", {"admin_id": user_id, "user_id": target_id, "duration": duration})
            await query.edit_message_text(f"✅ Пользователь {target_id} забанен на {duration}.")
        else:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("1 час", callback_data=f"ban_{target_id}_1h"),
                 InlineKeyboardButton("24 часа", callback_data=f"ban_{target_id}_24h")],
                [InlineKeyboardButton("7 дней", callback_data=f"ban_{target_id}_7d"),
                 InlineKeyboardButton("Навсегда", callback_data=f"ban_{target_id}_forever")],
                [InlineKeyboardButton("Отмена", callback_data="ban_cancel")]
            ])
            await query.edit_message_text(f"Выбери срок бана для {target_id}:", reply_markup=keyboard)

    # ---- Трекер бездействия: "Я здесь!" ----
    elif data.startswith("i_am_here_"):
        uid = int(data.split("_")[-1])
        if uid == update.effective_user.id:
            call_supabase("activity", {"user_id": uid})
            await query.edit_message_text("✅ Активность обновлена.")
        else:
            await query.edit_message_text("Это не твоя кнопка.")

    elif data == "ban_cancel":
        await query.edit_message_text("Отменено.")

# ========== ОБРАБОТКА СООБЩЕНИЙ В ГРУППЕ (ИИ) ==========
async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return

    bot = context.bot
    bot_username = (await bot.get_me()).username
    text = update.message.text or ""
    is_mention = f"@{bot_username}" in text
    is_reply_to_bot = (update.message.reply_to_message and
                       update.message.reply_to_message.from_user.id == bot.id)

    if not (is_mention or is_reply_to_bot):
        return

    user_id = update.effective_user.id
    if is_reply_to_bot:
        thread_id = update.message.reply_to_message.message_id
    else:
        thread_id = update.message.message_id

    result = call_supabase("ai_reply", {
        "user_id": user_id,
        "thread_id": thread_id,
        "message": text
    })
    if "reply" in result:
        reply_text = result["reply"]
        await update.message.reply_text(reply_text)
    else:
        await update.message.reply_text("Извини, я сейчас не в духе. Позже.")

# ========== ЗАГРУЗКА ФАЙЛОВ (КОМПРОМАТ) ==========
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id, context.bot):
        await update.message.reply_text("Доступ запрещён.")
        return

    doc = update.message.document
    if not doc:
        return
    caption = update.message.caption or ""
    if not caption.startswith("#"):
        await update.message.reply_text("Добавь подпись с тегом, например #tag")
        return
    tag = caption[1:].strip()

    # Отправляем в канал-хранилище
    bot = context.bot
    sent = await bot.send_document(chat_id=STORAGE_CHANNEL_ID, document=doc.file_id, caption=f"#{tag}")
    file_id = sent.document.file_id

    result = call_supabase("add_compromat", {"tag": tag, "file_id": file_id})
    if "ok" in result:
        await update.message.reply_text(f"✅ Файл сохранён с тегом #{tag}")
    else:
        await update.message.reply_text("Ошибка сохранения.")

# ========== ФОНОВАЯ ЗАДАЧА: ТРЕКЕР БЕЗДЕЙСТВИЯ ==========
async def inactivity_checker(context: ContextTypes.DEFAULT_TYPE):
    """Проверяет неактивных пользователей и отправляет предупреждение."""
    result = call_supabase("check_inactivity", {})
    if "inactive" in result:
        bot = context.bot
        for uid in result["inactive"]:
            try:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("Я здесь!", callback_data=f"i_am_here_{uid}")]
                ])
                await bot.send_message(
                    chat_id=uid,
                    text="Потерял интерес, сладенький, может кикнуть?",
                    reply_markup=keyboard
                )
            except Exception as e:
                print(f"Не удалось отправить предупреждение {uid}: {e}")

# ========== ГЛАВНАЯ ФУНКЦИЯ ==========
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reload_config", reload_config))

    # Обработчик главного меню (ReplyKeyboard)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handle_menu_buttons
    ))

    # Обработчик ввода текста (состояния)
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

    # --- Фоновая задача для трекера бездействия (каждые 24 часа) ---
    job_queue = application.job_queue
    if job_queue:
        # Запускаем через 10 секунд после старта, затем каждые 86400 секунд (24 часа)
        job_queue.run_repeating(inactivity_checker, interval=86400, first=10)
    else:
        print("JobQueue не доступен, трекер бездействия не запущен.")

    # Загружаем конфиг при старте
    load_config_from_telegram(application.bot)

    print("Бот запущен в режиме polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
