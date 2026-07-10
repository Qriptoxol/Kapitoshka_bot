from telegram import InlineKeyboardMarkup, InlineKeyboardButton

def send_inactive_warning(bot, user_id):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Я здесь!", callback_data=f"i_am_here_{user_id}")]
    ])
    bot.send_message(
        chat_id=user_id,
        text="Потерял интерес, сладенький, может кикнуть?",
        reply_markup=keyboard
    )
