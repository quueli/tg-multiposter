import asyncio
import logging

from aiogram import Bot, Dispatcher

import actions
import commands
import compose
from config import BOT_TOKEN, OWNER_ID
from scheduler import run_scheduler
from storage import data, load_data, save_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(commands.router)
dp.include_router(actions.router)
dp.include_router(compose.router)  # last, it eats every other private message


async def main():
    load_data()
    asyncio.create_task(run_scheduler(bot, data, save_data))

    logger.info(f"bot running for owner {OWNER_ID}")
    logger.info(f"groups: {len(data['groups'])}")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
