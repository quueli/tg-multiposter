import asyncio
import logging
import secrets
from datetime import datetime
from typing import Callable, Dict, List, Optional

from sender import multipost

logger = logging.getLogger(__name__)

POLL_INTERVAL = 15


def schedule_post(data: Dict, payload: Dict, send_at: Optional[datetime] = None,
                  owner_chat_id: Optional[int] = None) -> Dict:
    entry = {
        "id": secrets.token_hex(4),
        "send_at": (send_at or datetime.now()).isoformat(),
        "owner_chat_id": owner_chat_id,
        "pin": payload.get("pin", False),
        "media_list": payload.get("media_list", []),
        "text": payload.get("text"),
        "text_entities": payload.get("text_entities"),
        "is_media_group": payload.get("is_media_group", False),
    }
    data.setdefault("scheduled", []).append(entry)
    return entry


def due_posts(scheduled: List[Dict], now: datetime) -> List[Dict]:
    return [p for p in scheduled if datetime.fromisoformat(p["send_at"]) <= now]


async def process_due(bot, data: Dict, save_fn: Callable[[], None], now: Optional[datetime] = None) -> List[Dict]:
    now = now or datetime.now()
    scheduled = data.setdefault("scheduled", [])
    fired = []

    for post in due_posts(scheduled, now):
        result = await multipost(
            bot,
            data.get("groups", []),
            media_list=post.get("media_list"),
            text=post.get("text"),
            text_entities=post.get("text_entities"),
            is_media_group=post.get("is_media_group", False),
            pin=post.get("pin", False),
        )
        fired.append({"post": post, "result": result})
        data["scheduled"] = [p for p in data["scheduled"] if p["id"] != post["id"]]
        save_fn()

        owner_chat_id = post.get("owner_chat_id")
        if owner_chat_id:
            try:
                await bot.send_message(
                    owner_chat_id,
                    f"Scheduled post sent: {result['success']}/{result['total']} groups"
                )
            except Exception as e:
                logger.warning(f"could not report scheduled send to {owner_chat_id}: {e}")

    return fired


async def run_scheduler(bot, data: Dict, save_fn: Callable[[], None], poll_interval: float = POLL_INTERVAL):
    while True:
        await asyncio.sleep(poll_interval)
        try:
            await process_due(bot, data, save_fn)
        except Exception as e:
            logger.error(f"scheduler tick failed: {e}")
