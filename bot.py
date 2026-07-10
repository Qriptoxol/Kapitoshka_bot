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

# --- теперь импорты ---
import logging
import threading
import time
import requests
import json
from datetime import datetime
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

# ---------- НАСТРОЙКИ ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
STORAGE_CHANNEL_ID = int(os.environ.get("STORAGE_CHANNEL_ID", 0))

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

EDGE_FUNCTION_URL = f"{SUPABASE_URL}/functions/v1/main"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
}

# Состояния для ConversationHandler
WAITING_CODE, WAITING_TAG_AND_HOURS, WAITING_BAN_USER_ID, WAITING_UNBAN, WAITING_RESET_PENALTIES = range(5)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- РАБОТА С SUPABASE ----------
def call_supabase(action, params=None):
    payload = {"action": action, **(params or {})}
    try:
        resp = requests.post(EDGE_FUNCTION_URL, json=payload, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text}"}
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

def get_setting(key):
    res = call_supabase("get_setting", {"key": key})
    return res.get("value")

def set_setting(key, value):
    return call_supabase("set_setting", {"key": key, "value": value})

def get_user(user_id):
    return call_supabase("get_user", {"user_id": user_id})

def register_user(user_id, username, ref_code):
    return call_supabase("register", {
        "user_id": user_id,
        "username": username,
        "referrer_code": ref_code
    })

def update_activity(user_id):
    return call_supabase("activity", {"user_id": user_id})

def get_referral_link(user_id):
    return call_supabase("referral", {"user_id": user_id})

def activate_code(user_id, code):
    return call_supabase("activate_code", {"user_id": user_id, "code": code})

def get_file(file_tag):
    return call_supabase("get_file", {"file_tag": file_tag})

def add_compromat(tag, file_id):
    return call_supabase("add_compromat", {"tag": tag, "file_id": file_id})

def gen_code(admin_id, file_tag, hours):
    return call_supabase("gen_code", {"admin_id": admin_id, "file_tag": file_tag, "hours": hours})

def list_codes():
    return call_supabase("list_codes", {})

def ban_user(admin_id, user_id, duration):
    return call_supabase("ban", {"admin_id": admin_id, "user_id": user_id, "duration": duration})

def unban_user(user_id):
    return call_supabase("unban", {"user_id": user_id})

def reset_penalties(user_id):
    return call_supabase("reset_penalties", {"user_id": user_id})

def get_inactive_users():
    return call_supabase("check_inactivity", {})

def ai_reply(user_id, thread_id, message):
    return call_supabase("ai_reply", {
        "user_id": user_id,
        "thread_id": thread_id,
        "message": message
    })

def create_suspicion(user_id, type_, weight, details):
    return call_supabase("create_suspicion", {
        "user_id": user_id,
        "type": type_,
        "weight": weight,
        "details": details
    })

def resolve_suspicion(suspicion_id, resolution, admin_id):
    return call_supabase("resolve_suspicion", {
        "suspicion_id": suspicion_id,
        "resolution": resolution,
        "admin_id": admin_id
    })

def get_suspicion(suspicion_id):
    return call_supabase("get_suspicion", {"suspicion_id": suspicion_id})

def get_suspicion_details(suspicion_id):
    return call_supabase("get_suspicion_details", {"suspicion_id": suspicion_id})

def log_forward(user_id, message_id):
    return call_supabase("log_forward", {
        "user_id": user_id,
        "message_id_in_channel": message_id
    })

def get_forward_stats(user_id, hours=24):
    return call_supabase("get_forward_stats", {"user_id": user_id, "hours": hours})

def get_state(user_id):
    return call_supabase("get_state", {"user_id": user_id}).get("state")

def set_state(user_id, state):
    return call_supabase("set_state", {"user_id": user_id, "state": state})

def clear_state(user_id):
    return call_supabase("clear_state", {"user_id": user_id})

def set_lockdown(enabled):
    return call_supabase("lockdown", {"enabled": enabled})

# ---------- РАБОТА С КОНФИГОМ ----------
_config_cache = None
_config_last_update = None

def load_config_from_channel(bot):
    global _config_cache, _config_last_update
    file_id = get_setting("config_file_id")
    if file_id:
        try:
            file = bot.get_file(file_id)
            url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
            resp = requests.get(url)
            if resp.status_code == 200:
                config = json.loads(resp.text)
                _config_cache = config
                _config_last_update = datetime.now()
                logger.info("✅ Конфиг загружен из канала.")
                return config
        except Exception as e:
            logger.error(f"Ошибка загрузки конфига: {e}")

    logger.warning("⚠️ Конфиг не найден. Создаю новый и отправляю в канал.")
    config = DEFAULT_CONFIG.copy()
    sent = bot.send_document(
        chat_id=STORAGE_CHANNEL_ID,
        document=json.dumps(config, indent=2).encode('utf-8'),
        filename="config.json",
        caption="Конфиг бота (автосозданный)"
    )
    file_id = sent.document.file_id
    set_setting("config_file_id", file_id)
    _config_cache = config
    _config_last_update = datetime.now()
    logger.info("✅ Конфиг сохранён в канале и file_id записан в БД.")
    return config

def get_config(bot=None, force_reload=False):
    global _config_cache, _config_last_update
    if force_reload or _config_cache is None or (
        datetime.now() - _config_last_update).total_seconds() > 300:
        if bot:
            return load_config_from_channel(bot)
        else:
            return _config_cache or DEFAULT_CONFIG
    return _config_cache

def is_admin(user_id, bot=None):
    config = get_config(bot)
    return user_id in config.get("admins", [])

# ---------- ОБРАБОТЧИКИ ----------
def start(update, context):
    user = update.effective_user
    user_id = user.id
    username = user.username or ""
    ref_code = context.args[0] if context.args else None

    if not ref_code:
        update.message.reply_text(
            "❌ Доступ только по приглашению.\n"
            "Попроси друга дать тебе реферальную ссылку."
        )
        return

    result = register_user(user_id, username, ref_code)
    if "error" in result:
        update.message.reply_text("Ошибка регистрации. Попробуйте позже.")
        return

    update_activity(user_id)
    config = get_config(context.bot)
    main_link = config.get("main_channel_link", "https://t.me/your_main_channel")

    keyboard = [
        ["📎 Моя реф. ссылка", "🔑 Активировать код"],
    ]
    if is_admin(user_id, context.bot):
        keyboard.append(["⚙️ Админ-панель"])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    update.message.reply_text(
        f"👋 Привет, {username}!\n"
        f"Ты зарегистрирован по приглашению.\n"
        f"Теперь ты можешь присоединиться к главному каналу: {main_link}\n\n"
        "Выбери действие:",
        reply_markup=reply_markup
    )

def reload_config(update, context):
    if not is_admin(update.effective_user.id, context.bot):
        update.message.reply_text("Доступ запрещён.")
        return
    get_config(context.bot, force_reload=True)
    update.message.reply_text("Конфиг перезагружен.")

def handle_menu_buttons(update, context):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "📎 Моя реф. ссылка":
        result = get_referral_link(user_id)
        if "code" in result:
            bot_username = context.bot.get_me().username
            ref_link = f"https://t.me/{bot_username}?start={result['code']}"
            update.message.reply_text(f"Твоя ссылка:\n{ref_link}")
        else:
            update.message.reply_text("Не удалось создать ссылку.")

    elif text == "🔑 Активировать код":
        update.message.reply_text("Введи кодовое слово (промокод):")
        set_state(user_id, WAITING_CODE)
        return WAITING_CODE

    elif text == "⚙️ Админ-панель":
        if not is_admin(user_id, context.bot):
            update.message.reply_text("Доступ запрещён.")
            return
        keyboard = [
            ["➕ Добавить компромат", "🎫 Создать код"],
            ["📋 Список кодов", "🚫 Бан пользователя"],
            ["🔓 Разбан", "🔄 Сброс штрафов"],
            ["🔒 Lockdown", "🔓 Unlock"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        update.message.reply_text("Админ-панель:", reply_markup=reply_markup)

    elif text == "➕ Добавить компромат":
        if not is_admin(user_id, context.bot):
            return
        update.message.reply_text("Отправь файл и в подписи укажи тег (например, #tag).")

    elif text == "🎫 Создать код":
        if not is_admin(user_id, context.bot):
            return
        update.message.reply_text("Введи тег файла и срок в часах через пробел: тег 24")
        set_state(user_id, WAITING_TAG_AND_HOURS)
        return WAITING_TAG_AND_HOURS

    elif text == "📋 Список кодов":
        if not is_admin(user_id, context.bot):
            return
        res = list_codes()
        if "codes" in res:
            lines = [f"{c['code']} → {c['file_tag']} (exp: {c['expires_at']})" for c in res['codes']]
            update.message.reply_text("\n".join(lines) or "Нет активных кодов.")
        else:
            update.message.reply_text("Ошибка получения списка.")

    elif text == "🚫 Бан пользователя":
        if not is_admin(user_id, context.bot):
            return
        update.message.reply_text("Введи ID пользователя для бана:")
        set_state(user_id, WAITING_BAN_USER_ID)
        return WAITING_BAN_USER_ID

    elif text == "🔓 Разбан":
        if not is_admin(user_id, context.bot):
            return
        update.message.reply_text("Введи ID пользователя для разбана:")
        set_state(user_id, WAITING_UNBAN)
        return WAITING_UNBAN

    elif text == "🔄 Сброс штрафов":
        if not is_admin(user_id, context.bot):
            return
        update.message.reply_text("Введи ID пользователя для сброса штрафов:")
        set_state(user_id, WAITING_RESET_PENALTIES)
        return WAITING_RESET_PENALTIES

    elif text in ("🔒 Lockdown", "🔓 Unlock"):
        if not is_admin(user_id, context.bot):
            return
        enabled = text == "🔒 Lockdown"
        set_lockdown(enabled)
        update.message.reply_text(f"Режим {'Lockdown включён' if enabled else 'Unlock отключён'}.")

    return ConversationHandler.END

def handle_text_input(update, context):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = get_state(user_id)

    if state == WAITING_CODE:
        result = activate_code(user_id, text)
        if "error" in result:
            update.message.reply_text(f"❌ {result['error']}")
        else:
            file_tag = result.get("file_tag")
            if file_tag:
                file_res = get_file(file_tag)
                if "file_id" in file_res:
                    update.message.reply_text("✅ Код активирован! Вот файл:")
                    context.bot.send_document(chat_id=user_id, document=file_res["file_id"])
                else:
                    update.message.reply_text("Файл не найден.")
        clear_state(user_id)

    elif state == WAITING_TAG_AND_HOURS:
        parts = text.split()
        if len(parts) != 2:
            update.message.reply_text("Введи тег и часы через пробел, например: secret 24")
            return
        tag, hours_str = parts
        try:
            hours = int(hours_str)
        except ValueError:
            update.message.reply_text("Часы должны быть числом.")
            return
        result = gen_code(user_id, tag, hours)
        if "code" in result:
            update.message.reply_text(f"✅ Код создан: {result['code']}\nДействует до {result['expires_at']}")
        else:
            update.message.reply_text(f"Ошибка: {result.get('error', 'неизвестная')}")
        clear_state(user_id)

    elif state == WAITING_BAN_USER_ID:
        try:
            target_id = int(text)
        except ValueError:
            update.message.reply_text("ID должен быть числом.")
            return
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("1 час", callback_data=f"ban_{target_id}_1h"),
             InlineKeyboardButton("24 часа", callback_data=f"ban_{target_id}_24h")],
            [InlineKeyboardButton("7 дней", callback_data=f"ban_{target_id}_7d"),
             InlineKeyboardButton("Навсегда", callback_data=f"ban_{target_id}_forever")],
            [InlineKeyboardButton("Отмена", callback_data="ban_cancel")]
        ])
        update.message.reply_text(f"Выбери срок бана для {target_id}:", reply_markup=keyboard)
        clear_state(user_id)

    elif state == WAITING_UNBAN:
        try:
            target_id = int(text)
        except ValueError:
            update.message.reply_text("ID должен быть числом.")
            return
        unban_user(target_id)
        update.message.reply_text(f"Пользователь {target_id} разбанен.")
        clear_state(user_id)

    elif state == WAITING_RESET_PENALTIES:
        try:
            target_id = int(text)
        except ValueError:
            update.message.reply_text("ID должен быть числом.")
            return
        reset_penalties(target_id)
        update.message.reply_text(f"Штрафы для {target_id} сброшены.")
        clear_state(user_id)

    else:
        update.message.reply_text("Неизвестная команда. Используй /start")

def handle_callback(update, context):
    query = update.callback_query
    query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data.startswith("suspect_"):
        parts = data.split("_")
        suspicion_id = int(parts[1])
        action = parts[2]
        if action == "false":
            resolve_suspicion(suspicion_id, "false_positive", user_id)
            query.edit_message_text("✅ Помечено как ложное срабатывание.")
        elif action == "ban":
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("1 час", callback_data=f"ban_suspect_{suspicion_id}_1h"),
                 InlineKeyboardButton("24 часа", callback_data=f"ban_suspect_{suspicion_id}_24h")],
                [InlineKeyboardButton("7 дней", callback_data=f"ban_suspect_{suspicion_id}_7d"),
                 InlineKeyboardButton("Навсегда", callback_data=f"ban_suspect_{suspicion_id}_forever")],
                [InlineKeyboardButton("Отмена", callback_data="ban_cancel")]
            ])
            query.edit_message_text("Выбери срок бана:", reply_markup=keyboard)
        elif action == "proof":
            details = get_suspicion_details(suspicion_id)
            if "error" not in details:
                report = f"📄 Отчёт по подозрению #{suspicion_id}\n"
                report += f"Пользователь: {details.get('username', 'unknown')} (ID: {details.get('user_id')})\n"
                report += f"Тип: {details.get('type')}\n"
                report += f"Вес: {details.get('weight')}\n"
                report += f"Детали: {json.dumps(details.get('details', {}), indent=2, ensure_ascii=False)}"
                query.message.reply_text(report[:4096])
            else:
                query.message.reply_text("Не удалось загрузить пруфы.")

    elif data.startswith("ban_suspect_"):
        parts = data.split("_")
        suspicion_id = int(parts[2])
        duration = parts[3]
        if duration == "cancel":
            query.edit_message_text("Отменено.")
            return
        susp = get_suspicion(suspicion_id)
        if "user_id" in susp:
            target_id = susp["user_id"]
            ban_user(user_id, target_id, duration)
            query.edit_message_text(f"✅ Пользователь {target_id} забанен на {duration}.")
        else:
            query.edit_message_text("Ошибка получения данных.")

    elif data.startswith("ban_"):
        parts = data.split("_")
        target_id = int(parts[1])
        duration = parts[2] if len(parts) > 2 else None
        if duration == "cancel":
            query.edit_message_text("Отменено.")
            return
        if duration:
            ban_user(user_id, target_id, duration)
            query.edit_message_text(f"✅ Пользователь {target_id} забанен на {duration}.")
        else:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("1 час", callback_data=f"ban_{target_id}_1h"),
                 InlineKeyboardButton("24 часа", callback_data=f"ban_{target_id}_24h")],
                [InlineKeyboardButton("7 дней", callback_data=f"ban_{target_id}_7d"),
                 InlineKeyboardButton("Навсегда", callback_data=f"ban_{target_id}_forever")],
                [InlineKeyboardButton("Отмена", callback_data="ban_cancel")]
            ])
            query.edit_message_text(f"Выбери срок бана для {target_id}:", reply_markup=keyboard)

    elif data.startswith("i_am_here_"):
        uid = int(data.split("_")[-1])
        if uid == update.effective_user.id:
            update_activity(uid)
            query.edit_message_text("✅ Активность обновлена.")
        else:
            query.edit_message_text("Это не твоя кнопка.")

    elif data == "ban_cancel":
        query.edit_message_text("Отменено.")

def handle_group_message(update, context):
    if not update.message:
        return
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return

    bot = context.bot
    bot_username = bot.get_me().username
    text = update.message.text or ""
    is_mention = f"@{bot_username}" in text
    is_reply_to_bot = (update.message.reply_to_message and
                       update.message.reply_to_message.from_user.id == bot.id)

    if not (is_mention or is_reply_to_bot):
        return

    user_id = update.effective_user.id
    thread_id = update.message.reply_to_message.message_id if is_reply_to_bot else update.message.message_id

    result = ai_reply(user_id, thread_id, text)
    if "reply" in result:
        update.message.reply_text(result["reply"])
    else:
        update.message.reply_text("Извини, я сейчас не в духе. Позже.")

def handle_document(update, context):
    user_id = update.effective_user.id
    if not is_admin(user_id, context.bot):
        update.message.reply_text("Доступ запрещён.")
        return

    doc = update.message.document
    if not doc:
        return
    caption = update.message.caption or ""
    if not caption.startswith("#"):
        update.message.reply_text("Добавь подпись с тегом, например #tag")
        return
    tag = caption[1:].strip()

    sent = context.bot.send_document(
        chat_id=STORAGE_CHANNEL_ID,
        document=doc.file_id,
        caption=f"#{tag}"
    )
    file_id = sent.document.file_id
    result = add_compromat(tag, file_id)
    if "ok" in result:
        update.message.reply_text(f"✅ Файл сохранён с тегом #{tag}")
    else:
        update.message.reply_text("Ошибка сохранения.")

def inactivity_checker(bot):
    result = get_inactive_users()
    if "inactive" in result:
        for uid in result["inactive"]:
            try:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("Я здесь!", callback_data=f"i_am_here_{uid}")]
                ])
                bot.send_message(
                    chat_id=uid,
                    text="Потерял интерес, сладенький, может кикнуть?",
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.error(f"Не удалось отправить предупреждение {uid}: {e}")

def start_inactivity_thread(bot):
    def run():
        while True:
            time.sleep(86400)
            inactivity_checker(bot)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()

def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    bot = updater.bot

    load_config_from_channel(bot)

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("reload_config", reload_config))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.private, handle_menu_buttons))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.private, handle_text_input))
    dp.add_handler(CallbackQueryHandler(handle_callback))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command & (Filters.group | Filters.supergroup), handle_group_message))
    dp.add_handler(MessageHandler(Filters.document & Filters.private, handle_document))

    start_inactivity_thread(bot)

    logger.info("Бот запущен в режиме polling...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
