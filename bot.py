import os
import json
import requests
import asyncio
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
app = Flask(__name__)
# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8944304831:AAGiZhHGK-DHD8e5GTiM23wQbXE7s_bnLIA"
SUPABASE_URL = "https://liboxekacquvznqyxxzp.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxpYm94ZWthY3F1dnpucXl4eHpwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODM2Mjg1OTAsImV4cCI6MjA5OTIwNDU5MH0.0oglCN9qNC1vWXX36Y40a1DW089o-C_6jB28bMuB1XY"
STORAGE_CHANNEL_ID = -1004426342852 # например, -1001234567890

EDGE_FUNCTION_URL = f"{SUPABASE_URL}/functions/v1/main"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
}

# Глобальный кеш конфига
CONFIG = None
CONFIG_LAST_UPDATE = None
CONFIG_CACHE_TTL = 300  # 5 минут

# Состояния для ConversationHandler
WAITING_CODE = 1
WAITING_TAG_AND_HOURS = 2
WAITING_BAN_USER_ID = 3

# ========== РАБОТА С КОНФИГОМ ==========
def load_config_from_telegram():
    """Скачивает config.json из канала-хранилища и возвращает dict."""
    global CONFIG, CONFIG_LAST_UPDATE
    try:
        # Ищем последний файл config.json в канале
        # Для простоты будем хранить один файл с именем config.json
        # Получаем file_id через getUpdates или храним в БД, но проще: при первом запуске
        # мы сами отправим файл в канал и запомним его file_id в переменной окружения.
        # Но для универсальности будем искать сообщение с документом, у которого filename == "config.json"
        # Это можно сделать через bot.get_chat_history, но это долго.
        # Альтернатива: хранить file_id в переменной окружения CONFIG_FILE_ID.
        # Добавим такую переменную.
        file_id = os.environ.get("CONFIG_FILE_ID")
        if not file_id:
            # Если нет, вернём дефолт
            return get_default_config()
        # Скачиваем файл
        # Используем requests для скачивания через Telegram API
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
        resp = requests.get(url).json()
        if not resp.get("ok"):
            return get_default_config()
        file_path = resp["result"]["file_path"]
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        config_content = requests.get(file_url).text
        config = json.loads(config_content)
        CONFIG = config
        CONFIG_LAST_UPDATE = datetime.now()
        return config
    except Exception as e:
        print(f"Ошибка загрузки конфига: {e}")
        return get_default_config()

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

def get_config():
    global CONFIG, CONFIG_LAST_UPDATE
    if CONFIG is None or (datetime.now() - CONFIG_LAST_UPDATE).total_seconds() > CONFIG_CACHE_TTL:
        return load_config_from_telegram()
    return CONFIG

def is_admin(user_id):
    return user_id in get_config().get("admins", [])

# ========== ВЫЗОВ EDGE FUNCTION ==========
def call_supabase(action, params):
    payload = {"action": action, **params}
    try:
        resp = requests.post(EDGE_FUNCTION_URL, json=payload, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text}"}
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
async def send_inactive_warning(bot, user_id):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Я здесь!", callback_data=f"i_am_here_{user_id}")]
    ])
    await bot.send_message(
        chat_id=user_id,
        text="Потерял интерес, сладенький, может кикнуть?",
        reply_markup=keyboard
    )

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
    if is_admin(user_id):
        keyboard.append(["⚙️ Админ-панель"])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        f"👋 Привет, {username}! Ты зарегистрирован. Выбери действие:",
        reply_markup=reply_markup
    )

async def reload_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Доступ запрещён.")
        return
    load_config_from_telegram()
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
        if not is_admin(user_id):
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
        if not is_admin(user_id): return
        await update.message.reply_text("Отправь файл и в подписи укажи тег (например, #tag).")

    elif text == "🎫 Создать код":
        if not is_admin(user_id): return
        await update.message.reply_text("Введи тег файла и срок в часах через пробел: тег 24")
        return WAITING_TAG_AND_HOURS

    elif text == "📋 Список кодов":
        if not is_admin(user_id): return
        # Запросим из БД через Edge Function (добавим действие list_codes)
        result = call_supabase("list_codes", {})
        if "codes" in result:
            lines = [f"{c['code']} → {c['file_tag']} (exp: {c['expires_at']})" for c in result['codes']]
            await update.message.reply_text("\n".join(lines) or "Нет активных кодов.")
        else:
            await update.message.reply_text("Ошибка получения списка.")

    elif text == "🚫 Бан пользователя":
        if not is_admin(user_id): return
        await update.message.reply_text("Введи ID пользователя для бана:")
        return WAITING_BAN_USER_ID

    elif text == "🔓 Разбан":
        if not is_admin(user_id): return
        await update.message.reply_text("Введи ID пользователя для разбана:")
        # Простой обработчик – ждём текст
        return WAITING_BAN_USER_ID  # reuse, но потом различим по контексту

    elif text == "🔄 Сброс штрафов":
        if not is_admin(user_id): return
        await update.message.reply_text("Введи ID пользователя для сброса штрафов:")
        return WAITING_BAN_USER_ID  # аналогично

    elif text == "🔒 Lockdown":
        if not is_admin(user_id): return
        call_supabase("lockdown", {"enabled": True})
        await update.message.reply_text("Режим Lockdown включён (новые входы заблокированы).")

    elif text == "🔓 Unlock":
        if not is_admin(user_id): return
        call_supabase("lockdown", {"enabled": False})
        await update.message.reply_text("Lockdown отключён.")

    elif text == "📊 Логи":
        if not is_admin(user_id): return
        # Отправляем последний файл логов из канала-хранилища
        # Для простоты будем искать файл с именем logs_latest.json
        # реализуем позже

# ========== ОБРАБОТКА ВВОДА ТЕКСТА (состояния) ==========
async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = context.user_data.get("state")

    if state == WAITING_CODE:
        # Активация кода
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
        # Ожидаем ввод "тег часы"
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
        # Генерируем код
        result = call_supabase("gen_code", {"admin_id": user_id, "file_tag": tag, "hours": hours})
        if "code" in result:
            await update.message.reply_text(f"✅ Код создан: {result['code']}\nДействует до {result['expires_at']}")
        else:
            await update.message.reply_text(f"Ошибка: {result.get('error', 'неизвестная')}")
        context.user_data.pop("state", None)

    elif state == WAITING_BAN_USER_ID:
        # Определяем, что именно мы ждём: бан, разбан или сброс штрафов
        # По тексту предыдущего сообщения можно понять, но проще сохранить действие в user_data
        action = context.user_data.get("ban_action", "ban")
        try:
            target_id = int(text)
        except ValueError:
            await update.message.reply_text("ID должен быть числом.")
            return
        if action == "ban":
            # Сначала узнаем у админа срок через инлайн-кнопки
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("1 час", callback_data=f"ban_{target_id}_1h"),
                 InlineKeyboardButton("24 часа", callback_data=f"ban_{target_id}_24h")],
                [InlineKeyboardButton("7 дней", callback_data=f"ban_{target_id}_7d"),
                 InlineKeyboardButton("Навсегда", callback_data=f"ban_{target_id}_forever")],
                [InlineKeyboardButton("Отмена", callback_data="ban_cancel")]
            ])
            await update.message.reply_text(f"Выбери срок бана для {target_id}:", reply_markup=keyboard)
        elif action == "unban":
            call_supabase("unban", {"user_id": target_id})
            await update.message.reply_text(f"Пользователь {target_id} разбанен.")
        elif action == "reset_penalties":
            call_supabase("reset_penalties", {"user_id": target_id})
            await update.message.reply_text(f"Штрафы для {target_id} сброшены.")
        context.user_data.pop("state", None)
        context.user_data.pop("ban_action", None)

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
        action = parts[2]  # false, ban, proof
        if action == "false":
            # Ложное срабатывание
            call_supabase("resolve_suspicion", {"suspicion_id": suspicion_id, "resolution": "false_positive", "admin_id": user_id})
            await query.edit_message_text("✅ Помечено как ложное срабатывание.")
        elif action == "ban":
            # Открываем выбор срока
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("1 час", callback_data=f"ban_suspect_{suspicion_id}_1h"),
                 InlineKeyboardButton("24 часа", callback_data=f"ban_suspect_{suspicion_id}_24h")],
                [InlineKeyboardButton("7 дней", callback_data=f"ban_suspect_{suspicion_id}_7d"),
                 InlineKeyboardButton("Навсегда", callback_data=f"ban_suspect_{suspicion_id}_forever")],
                [InlineKeyboardButton("Отмена", callback_data="ban_cancel")]
            ])
            await query.edit_message_text("Выбери срок бана:", reply_markup=keyboard)
        elif action == "proof":
            # Показать пруфы
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
        duration = parts[3]  # 1h, 24h, 7d, forever
        if duration == "cancel":
            await query.edit_message_text("Отменено.")
            return
        # Получаем user_id из подозрения
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
            # Если пришло просто ban_ без срока – открываем выбор
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
            # Обновляем активность
            call_supabase("activity", {"user_id": uid})
            await query.edit_message_text("✅ Активность обновлена.")
        else:
            await query.edit_message_text("Это не твоя кнопка.")

    # ---- Прочие ----
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
    # Определяем thread_id – ID первого сообщения в ветке
    if is_reply_to_bot:
        # Идём вверх по цепочке, пока не найдём сообщение от пользователя (не бота)
        # Для простоты используем message_id первого сообщения в цепочке
        # Можно хранить thread_id в БД при первом ответе, но здесь упростим:
        # берём message_id сообщения, на которое отвечаем
        thread_id = update.message.reply_to_message.message_id
    else:
        thread_id = update.message.message_id

    # Вызываем Edge Function ai_reply
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

# ========== ОБРАБОТКА ЗАГРУЗКИ ФАЙЛОВ (компромат) ==========
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
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

    # Сохраняем в БД через Edge Function
    result = call_supabase("add_compromat", {"tag": tag, "file_id": file_id})
    if "ok" in result:
        await update.message.reply_text(f"✅ Файл сохранён с тегом #{tag}")
    else:
        await update.message.reply_text("Ошибка сохранения.")

# ========== ЭНДПОИНТ ДЛЯ CRON (трекер бездействия) ==========
@app.route('/cron_check', methods=['GET'])
def cron_check():
    # Вызываем Edge Function check_inactivity
    result = call_supabase("check_inactivity", {})
    if "inactive" in result:
        # Асинхронно отправляем предупреждения
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        bot = application.bot
        for uid in result["inactive"]:
            loop.run_until_complete(send_inactive_warning(bot, uid))
        loop.close()
        return jsonify({"sent": len(result["inactive"])})
    return jsonify({"error": "No inactive users"})

# ========== НАСТРОЙКА FLASK И WEBHOOK ==========
application = Application.builder().token(BOT_TOKEN).build()

# Регистрация обработчиков
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("reload_config", reload_config))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_buttons))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_message))
application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

@app.route('/webhook', methods=['POST'])
async def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    webhook_url = "https://yourusername.pythonanywhere.com/webhook"  # замени
    s = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}")
    return s.text

if __name__ == '__main__':
    # Загружаем конфиг при старте
    load_config_from_telegram()
    app.run(host='0.0.0.0', port=8000)