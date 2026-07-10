from database import get_state, set_state, clear_state

class StateManager:
    @staticmethod
    def get(update):
        return get_state(update.effective_user.id)

    @staticmethod
    def set(update, state):
        set_state(update.effective_user.id, state)

    @staticmethod
    def clear(update):
        clear_state(update.effective_user.id)
