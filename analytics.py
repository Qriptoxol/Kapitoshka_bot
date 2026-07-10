import logging
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from database import get_inactive_users, update_activity, log_forward, get_forward_stats

logger = logging.getLogger(__name__)

def track_forward(user_id, message_id):
    log_forward(user_id, message_id)

def get_forward_count(user_id, hours=24):
    res = get_forward_stats(user_id, hours)
    return res.get("count", 0)

def inactivity_checker(bot):
    """Проверяет неактивных пользователей и отправляет предупреждение."""
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
