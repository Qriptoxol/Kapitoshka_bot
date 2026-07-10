from database import get_state, set_state, clear_state

class StateManager:
    @staticmethod
    def get(update):
        user_id = update.effective_user.id
        return get_state(user_id)

    @staticmethod
    def set(update, state):
        user_id = update.effective_user.id
        set_state(user_id, state)

    @staticmethod
    def clear(update):
        user_id = update.effective_user.id
        clear_state(user_id)
