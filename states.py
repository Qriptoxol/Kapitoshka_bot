from database import get_state, set_state, clear_state

class StateManager:
    """Менеджер состояний, хранит в БД."""

    @staticmethod
    async def get(update, context):
        user_id = update.effective_user.id
        state = get_state(user_id)
        return state

    @staticmethod
    async def set(update, context, state):
        user_id = update.effective_user.id
        set_state(user_id, state)

    @staticmethod
    async def clear(update, context):
        user_id = update.effective_user.id
        clear_state(user_id)