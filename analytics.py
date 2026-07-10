import logging
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from database import get_inactive_users

logger = logging.getLogger(__name__)

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
