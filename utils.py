from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def send_inactive_warning(bot, user_id):
    """Отправляет пользователю предупреждение о бездействии."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Я здесь!", callback_data=f"i_am_here_{user_id}")]
    ])
    await bot.send_message(
        chat_id=user_id,
        text="Потерял интерес, сладенький, может кикнуть?",
        reply_markup=keyboard
    )
