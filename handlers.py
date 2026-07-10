import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from config import get_config, is_admin
from database import (
    register_user, update_activity, get_referral_link,
    activate_code, get_file, gen_code, list_codes,
    ban_user, unban_user, reset_penalties,
    create_suspicion, resolve_suspicion, get_suspicion_details,
    ai_reply, set_state, clear_state
)
from analytics import track_forward, get_forward_count
from states import StateManager
import os
# Состояния (числовые константы)
WAITING_CODE = 1
WAITING_TAG_AND_HOURS = 2
WAITING_BAN_USER_ID = 3
WAITING_UNBAN = 4
WAITING_RESET_PENALTIES = 5

logger = logging.getLogger(__name__)

# ---------- Команда /start ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or ""

    # Проверяем наличие реферального кода
    ref_code = context.args[0] if context.args else None
    if not ref_code:
        await update.message.reply_text(
            "❌ Доступ только по приглашению.\n"
            "Попроси друга дать тебе реферальную ссылку."
        )
        return

    # Регистрация
    result = register_user(user_id, username, ref_code)
    if "error" in result:
        await update.message.reply_text("Ошибка регистрации. Попробуйте позже.")
        return

    # Обновляем активность
    update_activity(user_id)

    # Получаем ссылку на главный канал из конфига
    config = get_config(context.bot)
    main_channel_link = config.get("main_channel_link", "https://t.me/your_main_channel")

    # Главное меню
    keyboard = [
        ["📎 Моя реф. ссылка", "🔑 Активировать код"],
    ]
    if is_admin(user_id, context.bot):
        keyboard.append(["⚙️ Админ-панель"])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        f"👋 Привет, {username}!\n"
        f"Ты зарегистрирован по приглашению.\n"
        f"Теперь ты можешь присоединиться к главному каналу: {main_channel_link}\n\n"
        "Выбери действие:",
        reply_markup=reply_markup
    )

# ---------- Обработка кнопок меню ----------
async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "📎 Моя реф. ссылка":
        result = get_referral_link(user_id)
        if "code" in result:
            bot_username = (await context.bot.get_me()).username
            ref_link = f"https://t.me/{bot_username}?start={result['code']}"
            await update.message.reply_text(f"Твоя реферальная ссылка:\n{ref_link}")
        else:
            await update.message.reply_text("Не удалось создать ссылку.")

    elif text == "🔑 Активировать код":
        await update.message.reply_text("Введи кодовое слово (промокод):")
        await StateManager.set(update, context, WAITING_CODE)
        return WAITING_CODE

    elif text == "⚙️ Админ-панель":
        if not is_admin(user_id, context.bot):
            await update.message.reply_text("Доступ запрещён.")
            return
        keyboard = [
            ["➕ Добавить компромат", "🎫 Создать код"],
            ["📋 Список кодов", "🚫 Бан пользователя"],
            ["🔓 Разбан", "🔄 Сброс штрафов"],
            ["🔒 Lockdown", "🔓 Unlock"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Админ-панель:", reply_markup=reply_markup)

    # ---- Админские кнопки ----
    elif text == "➕ Добавить компромат":
        if not is_admin(user_id, context.bot): return ConversationHandler.END
        await update.message.reply_text("Отправь файл и в подписи укажи тег (например, #tag).")

    elif text == "🎫 Создать код":
        if not is_admin(user_id, context.bot): return ConversationHandler.END
        await update.message.reply_text("Введи тег файла и срок в часах через пробел: тег 24")
        await StateManager.set(update, context, WAITING_TAG_AND_HOURS)
        return WAITING_TAG_AND_HOURS

    elif text == "📋 Список кодов":
        if not is_admin(user_id, context.bot): return ConversationHandler.END
        res = list_codes()
        if "codes" in res:
            lines = [f"{c['code']} → {c['file_tag']} (exp: {c['expires_at']})" for c in res['codes']]
            await update.message.reply_text("\n".join(lines) or "Нет активных кодов.")
        else:
            await update.message.reply_text("Ошибка получения списка.")

    elif text == "🚫 Бан пользователя":
        if not is_admin(user_id, context.bot): return ConversationHandler.END
        await update.message.reply_text("Введи ID пользователя для бана:")
        await StateManager.set(update, context, WAITING_BAN_USER_ID)
        return WAITING_BAN_USER_ID

    elif text == "🔓 Разбан":
        if not is_admin(user_id, context.bot): return ConversationHandler.END
        await update.message.reply_text("Введи ID пользователя для разбана:")
        await StateManager.set(update, context, WAITING_UNBAN)
        return WAITING_UNBAN

    elif text == "🔄 Сброс штрафов":
        if not is_admin(user_id, context.bot): return ConversationHandler.END
        await update.message.reply_text("Введи ID пользователя для сброса штрафов:")
        await StateManager.set(update, context, WAITING_RESET_PENALTIES)
        return WAITING_RESET_PENALTIES

    elif text == "🔒 Lockdown":
        if not is_admin(user_id, context.bot): return ConversationHandler.END
        # Вызов lockdown через Edge Function (реализовать в функциях)
        # пока заглушка
        await update.message.reply_text("Функция в разработке.")

    elif text == "🔓 Unlock":
        if not is_admin(user_id, context.bot): return ConversationHandler.END
        await update.message.reply_text("Функция в разработке.")

    return ConversationHandler.END

# ---------- Обработка текстового ввода (состояния) ----------
async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = await StateManager.get(update, context)

    if state == WAITING_CODE:
        # Активация промокода
        result = activate_code(user_id, text)
        if "error" in result:
            await update.message.reply_text(f"❌ {result['error']}")
        else:
            file_tag = result.get("file_tag")
            if file_tag:
                file_res = get_file(file_tag)
                if "file_id" in file_res:
                    await update.message.reply_text("✅ Код активирован! Вот файл:")
                    await context.bot.send_document(chat_id=user_id, document=file_res["file_id"])
                else:
                    await update.message.reply_text("Файл не найден.")
        await StateManager.clear(update, context)

    elif state == WAITING_TAG_AND_HOURS:
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text("Введи тег и часы через пробел, например: secret 24")
            return
        tag, hours_str = parts
        try:
            hours = int(hours_str)
        except ValueError:
            await update.message.reply_text("Часы должны быть числом.")
            return
        result = gen_code(user_id, tag, hours)
        if "code" in result:
            await update.message.reply_text(f"✅ Код создан: {result['code']}\nДействует до {result['expires_at']}")
        else:
            await update.message.reply_text(f"Ошибка: {result.get('error', 'неизвестная')}")
        await StateManager.clear(update, context)

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
        await StateManager.clear(update, context)

    elif state == WAITING_UNBAN:
        try:
            target_id = int(text)
        except ValueError:
            await update.message.reply_text("ID должен быть числом.")
            return
        unban_user(target_id)
        await update.message.reply_text(f"Пользователь {target_id} разбанен.")
        await StateManager.clear(update, context)

    elif state == WAITING_RESET_PENALTIES:
        try:
            target_id = int(text)
        except ValueError:
            await update.message.reply_text("ID должен быть числом.")
            return
        reset_penalties(target_id)
        await update.message.reply_text(f"Штрафы для {target_id} сброшены.")
        await StateManager.clear(update, context)

    else:
        await update.message.reply_text("Неизвестная команда. Используй /start")

# ---------- Инлайн-колбэки ----------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    # ---- Подозрения ----
    if data.startswith("suspect_"):
        parts = data.split("_")
        suspicion_id = int(parts[1])
        action = parts[2]
        if action == "false":
            resolve_suspicion(suspicion_id, "false_positive", user_id)
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
            details = get_suspicion_details(suspicion_id)
            if "error" not in details:
                report = f"📄 Отчёт по подозрению #{suspicion_id}\n"
                report += f"Пользователь: {details.get('username', 'unknown')} (ID: {details.get('user_id')})\n"
                report += f"Тип: {details.get('type')}\n"
                report += f"Вес: {details.get('weight')}\n"
                report += f"Детали: {json.dumps(details.get('details', {}), indent=2, ensure_ascii=False)}"
                await query.message.reply_text(report[:4096])
            else:
                await query.message.reply_text("Не удалось загрузить пруфы.")

    # ---- Бан с выбором срока ----
    elif data.startswith("ban_suspect_"):
        parts = data.split("_")
        suspicion_id = int(parts[2])
        duration = parts[3]
        if duration == "cancel":
            await query.edit_message_text("Отменено.")
            return
        susp = get_suspicion(suspicion_id)
        if "user_id" in susp:
            target_id = susp["user_id"]
            ban_user(user_id, target_id, duration)
            await query.edit_message_text(f"✅ Пользователь {target_id} забанен на {duration}.")
        else:
            await query.edit_message_text("Ошибка получения данных.")

    # ---- Бан по ID (из админки) ----
    elif data.startswith("ban_"):
        parts = data.split("_")
        target_id = int(parts[1])
        duration = parts[2] if len(parts) > 2 else None
        if duration == "cancel":
            await query.edit_message_text("Отменено.")
            return
        if duration:
            ban_user(user_id, target_id, duration)
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

    # ---- Трекер бездействия ----
    elif data.startswith("i_am_here_"):
        uid = int(data.split("_")[-1])
        if uid == update.effective_user.id:
            update_activity(uid)
            await query.edit_message_text("✅ Активность обновлена.")
        else:
            await query.edit_message_text("Это не твоя кнопка.")

    elif data == "ban_cancel":
        await query.edit_message_text("Отменено.")

# ---------- Групповые сообщения (ИИ) ----------
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
    thread_id = update.message.reply_to_message.message_id if is_reply_to_bot else update.message.message_id

    result = ai_reply(user_id, thread_id, text)
    if "reply" in result:
        await update.message.reply_text(result["reply"])
    else:
        await update.message.reply_text("Извини, я сейчас не в духе. Позже.")

# ---------- Загрузка документов (компромат) ----------
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
    sent = await bot.send_document(chat_id=os.environ.get("STORAGE_CHANNEL_ID"), document=doc.file_id, caption=f"#{tag}")
    file_id = sent.document.file_id

    # Сохраняем в БД через Edge Function
    from database import add_compromat
    result = add_compromat(tag, file_id)
    if "ok" in result:
        await update.message.reply_text(f"✅ Файл сохранён с тегом #{tag}")
    else:
        await update.message.reply_text("Ошибка сохранения.")