from database import log_forward, get_forward_stats

def track_forward(user_id: int, message_id: int):
    """Записать факт пересылки."""
    log_forward(user_id, message_id)

def get_forward_count(user_id: int, hours: int = 24) -> int:
    """Получить количество пересылов за период."""
    res = get_forward_stats(user_id, hours)
    return res.get("count", 0)