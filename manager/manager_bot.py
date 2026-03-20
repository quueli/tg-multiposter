import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher

# started as a script, so the project root is not on the path yet
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from manager import admin, callbacks, handlers
from manager.config import ADMINS, BOT_TOKEN, INSTANCES_DIR, TEMPLATE_DIR
from manager.instances import running_processes, start_instance, stop_instance
from manager.storage import data, load_data
from manager.subscriptions import check_subscriptions, is_active

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(admin.router)
dp.include_router(callbacks.router)
dp.include_router(handlers.router)  # last, it eats every other private message


async def startup():
    load_data()
    os.makedirs(INSTANCES_DIR, exist_ok=True)
    os.makedirs(TEMPLATE_DIR, exist_ok=True)

    for record in data["users"].values():
        for bot_info in record.get("bots", []):
            if is_active(bot_info) and bot_info.get("instance_dir"):
                start_instance(bot_info["instance_dir"])

    logger.info(f"started {len(running_processes)} instances")


async def main():
    await startup()
    asyncio.create_task(check_subscriptions(bot))

    logger.info("manager bot running")
    logger.info(f"admins: {ADMINS}")
    logger.info(f"users: {len(data['users'])}")

    try:
        await dp.start_polling(bot)
    finally:
        for instance_dir in list(running_processes):
            stop_instance(instance_dir)


if __name__ == "__main__":
    asyncio.run(main())
