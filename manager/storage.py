import json
import logging
import os

from manager.config import ADMINS, DATA_FILE

logger = logging.getLogger(__name__)

data = {"users": {}}


def load_data():
    if not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            loaded = json.load(f)
    except Exception as e:
        logger.error(f"failed to load data: {e}")
        return

    if "subscriptions" in loaded:
        data["users"] = migrate_v1(loaded["subscriptions"])
    else:
        data["users"] = {str(k): v for k, v in loaded.get("users", {}).items()}


def migrate_v1(old_subs):
    # v1 kept a single bot per user with no list at all
    users = {}
    for user_id, info in old_subs.items():
        bots = []
        if info.get("bot_token"):
            bots.append({
                "bot_token": info["bot_token"],
                "bot_username": info.get("bot_username"),
                "instance_dir": info.get("instance_dir"),
                "expires": info.get("expires"),
            })
        users[str(user_id)] = {"pending_days": 0, "bots": bots}
    return users


def save_data():
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def is_admin(user_id: int) -> bool:
    return user_id in ADMINS


def get_user(user_id: int) -> dict:
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {"pending_days": 0, "bots": []}
    return data["users"][uid]


def get_bots(user_id: int) -> list:
    return get_user(user_id).get("bots", [])


def token_taken(token: str, user_id: int) -> bool:
    # one token, one instance, or two processes end up fighting over the same updates
    for uid, record in data["users"].items():
        if int(uid) == user_id:
            continue
        if any(b.get("bot_token") == token for b in record.get("bots", [])):
            return True
    return False
