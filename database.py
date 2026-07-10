import os
import requests
import json
from datetime import datetime
from typing import Optional, Dict, Any, List

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
EDGE_FUNCTION_URL = f"{SUPABASE_URL}/functions/v1/main"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
}

def call_supabase(action: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Универсальный вызов Edge Function."""
    payload = {"action": action, **(params or {})}
    try:
        resp = requests.post(EDGE_FUNCTION_URL, json=payload, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text}"}
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

# ---------- Пользователи ----------
def register_user(user_id: int, username: str, referrer_code: str = None) -> Dict:
    return call_supabase("register", {
        "user_id": user_id,
        "username": username,
        "referrer_code": referrer_code
    })

def get_user(user_id: int) -> Optional[Dict]:
    return call_supabase("get_user", {"user_id": user_id})

def update_activity(user_id: int) -> Dict:
    return call_supabase("activity", {"user_id": user_id})

def ban_user(admin_id: int, user_id: int, duration: str) -> Dict:
    return call_supabase("ban", {"admin_id": admin_id, "user_id": user_id, "duration": duration})

def unban_user(user_id: int) -> Dict:
    return call_supabase("unban", {"user_id": user_id})

def reset_penalties(user_id: int) -> Dict:
    return call_supabase("reset_penalties", {"user_id": user_id})

def get_referral_link(user_id: int) -> Dict:
    return call_supabase("referral", {"user_id": user_id})

# ---------- Реферальная система ----------
def activate_code(user_id: int, code: str) -> Dict:
    return call_supabase("activate_code", {"user_id": user_id, "code": code})

def get_file(file_tag: str) -> Dict:
    return call_supabase("get_file", {"file_tag": file_tag})

def add_compromat(tag: str, file_id: str) -> Dict:
    return call_supabase("add_compromat", {"tag": tag, "file_id": file_id})

def gen_code(admin_id: int, file_tag: str, hours: int) -> Dict:
    return call_supabase("gen_code", {"admin_id": admin_id, "file_tag": file_tag, "hours": hours})

def list_codes() -> Dict:
    return call_supabase("list_codes", {})

# ---------- Подозрения ----------
def create_suspicion(user_id: int, type_: str, weight: float, details: Dict) -> Dict:
    return call_supabase("create_suspicion", {
        "user_id": user_id,
        "type": type_,
        "weight": weight,
        "details": details
    })

def resolve_suspicion(suspicion_id: int, resolution: str, admin_id: int) -> Dict:
    return call_supabase("resolve_suspicion", {
        "suspicion_id": suspicion_id,
        "resolution": resolution,
        "admin_id": admin_id
    })

def get_suspicion(suspicion_id: int) -> Dict:
    return call_supabase("get_suspicion", {"suspicion_id": suspicion_id})

def get_suspicion_details(suspicion_id: int) -> Dict:
    return call_supabase("get_suspicion_details", {"suspicion_id": suspicion_id})

# ---------- Аналитика ----------
def log_forward(user_id: int, message_id_in_channel: int) -> Dict:
    return call_supabase("log_forward", {
        "user_id": user_id,
        "message_id_in_channel": message_id_in_channel
    })

def get_forward_stats(user_id: int, hours: int = 24) -> Dict:
    return call_supabase("get_forward_stats", {"user_id": user_id, "hours": hours})

def get_inactive_users() -> Dict:
    return call_supabase("check_inactivity", {})

# ---------- ИИ ----------
def ai_reply(user_id: int, thread_id: int, message: str) -> Dict:
    return call_supabase("ai_reply", {
        "user_id": user_id,
        "thread_id": thread_id,
        "message": message
    })

# ---------- Состояния бота (для ConversationHandler) ----------
def get_state(user_id: int) -> Optional[str]:
    """Получить текущее состояние пользователя из БД."""
    res = call_supabase("get_state", {"user_id": user_id})
    return res.get("state") if "state" in res else None

def set_state(user_id: int, state: str) -> Dict:
    """Сохранить состояние пользователя в БД."""
    return call_supabase("set_state", {"user_id": user_id, "state": state})

def clear_state(user_id: int) -> Dict:
    """Удалить состояние."""
    return call_supabase("clear_state", {"user_id": user_id})

# ---------- Настройки ----------
def get_setting(key: str) -> Optional[str]:
    res = call_supabase("get_setting", {"key": key})
    return res.get("value")

def set_setting(key: str, value: str) -> Dict:
    return call_supabase("set_setting", {"key": key, "value": value})