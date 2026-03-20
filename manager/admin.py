import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message

from manager import ui
from manager.storage import data, get_user, is_admin, save_data
from manager.subscriptions import add_pending, days_left, is_active, pending_days

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)


async def ensure_admin(message: Message) -> bool:
    if is_admin(message.from_user.id):
        return True
    await message.answer("This command is for admins only.")
    return False


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, bot: Bot):
    if not await ensure_admin(message):
        return

    args = message.text.split()
    if len(args) < 3:
        await message.answer("usage: /subscribe ID DAYS")
        return

    try:
        target_id = int(args[1])
        days = int(args[2])
    except ValueError:
        await message.answer("ID and DAYS must be numbers.")
        return

    if days <= 0:
        await message.answer("DAYS must be greater than 0.")
        return

    add_pending(target_id, days)
    total = pending_days(target_id)

    await message.answer(
        f"Added {days} days of subscription to {target_id}.\n"
        f"Pending, not yet assigned to a bot: {total} days"
    )

    try:
        await bot.send_message(
            target_id,
            ui.welcome(total),
            reply_markup=ui.choice_keyboard(target_id, total),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"could not notify {target_id}: {e}")
        await message.answer("Could not notify the user (they may not have started the bot).")


@router.message(Command("info"))
async def cmd_info(message: Message):
    if not await ensure_admin(message):
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("usage: /info ID")
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("ID must be a number.")
        return

    record = data["users"].get(str(target_id))
    if not record:
        await message.answer(f"No such user: {target_id}")
        return

    bots = record.get("bots", [])
    lines = [
        f"<b>User {target_id}</b>\n",
        f"Pending days: {record.get('pending_days', 0)}\n",
        f"Bots: {len(bots)}\n",
    ]

    for i, bot_info in enumerate(bots):
        status = "active" if is_active(bot_info) else "expired"
        lines.append(f"\n[{status}] bot {i + 1}: @{bot_info.get('bot_username', '???')}")
        lines.append(f"   expires: {bot_info.get('expires', '-')}")
        lines.append(f"   days left: {days_left(bot_info)}")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("list"))
async def cmd_list(message: Message):
    if not await ensure_admin(message):
        return

    if not data["users"]:
        await message.answer("No users yet.")
        return

    lines = ["<b>Users:</b>\n"]
    for user_id, record in data["users"].items():
        bots = record.get("bots", [])
        active = sum(1 for b in bots if is_active(b))
        lines.append(f"- {user_id}: {len(bots)} bots ({active} active), "
                     f"+{record.get('pending_days', 0)}d pending")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("create"))
async def cmd_create(message: Message):
    if not await ensure_admin(message):
        return

    # admins get a bot without spending subscription days
    record = get_user(message.from_user.id)
    record["pending_days"] = 36500
    record["admin_create"] = True
    save_data()

    await message.answer(ui.token_prompt(), parse_mode="HTML")
