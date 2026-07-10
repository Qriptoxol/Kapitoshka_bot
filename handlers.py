import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ConversationHandler
from config import get_config, is_admin
from database import (
    register_user, update_activity, get_referral_link,
    activate_code, get_file, gen_code, list_codes,
    ban_user, unban_user, reset_penalties,
    create_suspicion, resolve_suspicion, get_suspicion_details,
    ai_reply, set_state, clear_state, set_lockdown,
    add_compromat
)
from states import StateManager
from analytics import track_forward, get_forward_count

logger = logging.getLogger(__name__)

# Состояния
WAITING_CODE, WAITING_TAG_AND_HOURS, WAITING_BAN_USER_ID, WAITING_UNBAN, WAITING_RESET_PENALTIES = range(5)

# ---------- /start ----------
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

# ---------- /reload_config ----------
def reload_config(update, context):
    if not is_admin(update.effective_user.id, context.bot):
        update.message.reply_text("Доступ запрещён.")
        return
    get_config(context.bot, force_reload=True)
    update.message.reply_text("Конфиг перезагружен.")

# ---------- Кнопки меню ----------
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
        StateManager.set(update, WAITING_CODE)
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
        StateManager.set(update, WAITING_TAG_AND_HOURS)
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
        StateManager.set(update, WAITING_BAN_USER_ID)
        return WAITING_BAN_USER_ID

    elif text == "🔓 Разбан":
        if not is_admin(user_id, context.bot):
            return
        update.message.reply_text("Введи ID пользователя для разбана:")
        StateManager.set(update, WAITING_UNBAN)
        return WAITING_UNBAN

    elif text == "🔄 Сброс штрафов":
        if not is_admin(user_id, context.bot):
            return
        update.message.reply_text("Введи ID пользователя для сброса штрафов:")
        StateManager.set(update, WAITING_RESET_PENALTIES)
        return WAITING_RESET_PENALTIES

    elif text in ("🔒 Lockdown", "🔓 Unlock"):
        if not is_admin(user_id, context.bot):
            return
        enabled = text == "🔒 Lockdown"
        set_lockdown(enabled)
        update.message.reply_text(f"Режим {'Lockdown включён' if enabled else 'Unlock отключён'}.")

    return ConversationHandler.END

# ---------- Текстовый ввод (состояния) ----------
def handle_text_input(update, context):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = StateManager.get(update)

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
        StateManager.clear(update)

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
        StateManager.clear(update)

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
        StateManager.clear(update)

    elif state == WAITING_UNBAN:
        try:
            target_id = int(text)
        except ValueError:
            update.message.reply_text("ID должен быть числом.")
            return
        unban_user(target_id)
        update.message.reply_text(f"Пользователь {target_id} разбанен.")
        StateManager.clear(update)

    elif state == WAITING_RESET_PENALTIES:
        try:
            target_id = int(text)
        except ValueError:
            update.message.reply_text("ID должен быть числом.")
            return
        reset_penalties(target_id)
        update.message.reply_text(f"Штрафы для {target_id} сброшены.")
        StateManager.clear(update)

    else:
        update.message.reply_text("Неизвестная команда. Используй /start")

# ---------- Инлайн-колбэки ----------
def handle_callback(update, context):
    query = update.callback_query
    query.answer()
    data = query.data
    user_id = update.effective_user.id

    # Подозрения
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

# ---------- Сообщения в группе (ИИ) ----------
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

# ---------- Загрузка документов (компромат) ----------
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

    # Отправляем в канал-хранилище
    sent = context.bot.send_document(
        chat_id=int(os.environ.get("STORAGE_CHANNEL_ID")),
        document=doc.file_id,
        caption=f"#{tag}"
    )
    file_id = sent.document.file_id
    result = add_compromat(tag, file_id)
    if "ok" in result:
        update.message.reply_text(f"✅ Файл сохранён с тегом #{tag}")
    else:
        update.message.reply_text("Ошибка сохранения.")
