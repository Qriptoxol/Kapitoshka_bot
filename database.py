import os
import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
EDGE_FUNCTION_URL = f"{SUPABASE_URL}/functions/v1/main"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
}

def call_supabase(action, params=None):
    payload = {"action": action, **(params or {})}
    try:
        resp = requests.post(EDGE_FUNCTION_URL, json=payload, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text}"}
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

# ----- Настройки -----
def get_setting(key):
    res = call_supabase("get_setting", {"key": key})
    return res.get("value")

def set_setting(key, value):
    return call_supabase("set_setting", {"key": key, "value": value})

# ----- Пользователи -----
def get_user(user_id):
    return call_supabase("get_user", {"user_id": user_id})

def register_user(user_id, username, ref_code):
    return call_supabase("register", {
        "user_id": user_id,
        "username": username,
        "referrer_code": ref_code
    })

def update_activity(user_id):
    return call_supabase("activity", {"user_id": user_id})

def get_referral_link(user_id):
    return call_supabase("referral", {"user_id": user_id})

def ban_user(admin_id, user_id, duration):
    return call_supabase("ban", {"admin_id": admin_id, "user_id": user_id, "duration": duration})

def unban_user(user_id):
    return call_supabase("unban", {"user_id": user_id})

def reset_penalties(user_id):
    return call_supabase("reset_penalties", {"user_id": user_id})

def get_inactive_users():
    return call_supabase("check_inactivity", {})

# ----- Кодовые слова и компромат -----
def activate_code(user_id, code):
    return call_supabase("activate_code", {"user_id": user_id, "code": code})

def get_file(file_tag):
    return call_supabase("get_file", {"file_tag": file_tag})

def add_compromat(tag, file_id):
    return call_supabase("add_compromat", {"tag": tag, "file_id": file_id})

def gen_code(admin_id, file_tag, hours):
    return call_supabase("gen_code", {"admin_id": admin_id, "file_tag": file_tag, "hours": hours})

def list_codes():
    return call_supabase("list_codes", {})

# ----- ИИ -----
def ai_reply(user_id, thread_id, message):
    return call_supabase("ai_reply", {
        "user_id": user_id,
        "thread_id": thread_id,
        "message": message
    })

# ----- Подозрения -----
def create_suspicion(user_id, type_, weight, details):
    return call_supabase("create_suspicion", {
        "user_id": user_id,
        "type": type_,
        "weight": weight,
        "details": details
    })

def resolve_suspicion(suspicion_id, resolution, admin_id):
    return call_supabase("resolve_suspicion", {
        "suspicion_id": suspicion_id,
        "resolution": resolution,
        "admin_id": admin_id
    })

def get_suspicion(suspicion_id):
    return call_supabase("get_suspicion", {"suspicion_id": suspicion_id})

def get_suspicion_details(suspicion_id):
    return call_supabase("get_suspicion_details", {"suspicion_id": suspicion_id})

# ----- Логи пересылов -----
def log_forward(user_id, message_id):
    return call_supabase("log_forward", {
        "user_id": user_id,
        "message_id_in_channel": message_id
    })

def get_forward_stats(user_id, hours=24):
    return call_supabase("get_forward_stats", {"user_id": user_id, "hours": hours})

# ----- Состояния -----
def get_state(user_id):
    return call_supabase("get_state", {"user_id": user_id}).get("state")

def set_state(user_id, state):
    return call_supabase("set_state", {"user_id": user_id, "state": state})

def clear_state(user_id):
    return call_supabase("clear_state", {"user_id": user_id})

# ----- Lockdown -----
def set_lockdown(enabled):
    return call_supabase("lockdown", {"enabled": enabled})
