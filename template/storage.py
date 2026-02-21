import json
import logging
import os

from config import DATA_FILE

logger = logging.getLogger(__name__)

data = {
    "groups": [],
    "scheduled": [],
}


def load_data():
    if not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            loaded = json.load(f)
    except Exception as e:
        logger.error(f"failed to load data: {e}")
        return

    data["groups"] = loaded.get("groups", [])
    data["scheduled"] = loaded.get("scheduled", [])


def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def register_group(chat_id, title) -> bool:
    if any(g["id"] == chat_id for g in data["groups"]):
        return False
    data["groups"].append({"id": chat_id, "title": title or "Untitled"})
    save_data()
    logger.info(f"registered group {title} ({chat_id})")
    return True


def drop_groups(chat_ids):
    data["groups"] = [g for g in data["groups"] if g["id"] not in chat_ids]
    save_data()
