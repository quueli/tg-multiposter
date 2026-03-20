import asyncio
import logging
from datetime import datetime, timedelta

from manager.config import SUPPORT_CONTACT
from manager.instances import running_processes, start_instance, stop_instance
from manager.storage import data, get_user, is_admin, save_data

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 60


def is_active(bot_info) -> bool:
    expires = bot_info.get("expires")
    return bool(expires) and datetime.fromisoformat(expires) > datetime.now()


def days_left(bot_info) -> int:
    expires = bot_info.get("expires")
    if not expires:
        return 0
    return max(0, (datetime.fromisoformat(expires) - datetime.now()).days)


def pending_days(user_id) -> int:
    return get_user(user_id).get("pending_days", 0)


def set_pending(user_id, days):
    get_user(user_id)["pending_days"] = days
    save_data()


def add_pending(user_id, days):
    record = get_user(user_id)
    record["pending_days"] = record.get("pending_days", 0) + days
    save_data()


def extend(user_id, bot_index, days) -> bool:
    bots = get_user(user_id).get("bots", [])
    if bot_index >= len(bots):
        return False

    bot_info = bots[bot_index]
    base = datetime.now()
    expires = bot_info.get("expires")
    if expires:
        current = datetime.fromisoformat(expires)
        if current > base:
            base = current

    bot_info["expires"] = (base + timedelta(days=days)).isoformat()
    save_data()
    return True


async def check_subscriptions(bot, interval=CHECK_INTERVAL):
    notified = set()

    while True:
        await asyncio.sleep(interval)

        for user_id, record in list(data["users"].items()):
            if is_admin(int(user_id)):
                continue

            for bot_info in record.get("bots", []):
                instance_dir = bot_info.get("instance_dir")
                if not instance_dir:
                    continue

                username = bot_info.get("bot_username", "")
                key = f"{user_id}_{username}"

                if is_active(bot_info):
                    notified.discard(key)
                    if instance_dir not in running_processes:
                        start_instance(instance_dir)
                    continue

                if instance_dir in running_processes:
                    stop_instance(instance_dir)
                if key in notified:
                    continue

                try:
                    await bot.send_message(
                        int(user_id),
                        f"<b>Subscription for @{username} has expired</b>\n\n"
                        f"The bot has been stopped.\n"
                        f"Contact {SUPPORT_CONTACT} to renew.",
                        parse_mode="HTML"
                    )
                    notified.add(key)
                except Exception as e:
                    logger.warning(f"could not notify {user_id}: {e}")
