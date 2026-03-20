import logging
import re
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message

from manager import ui
from manager.config import SUPPORT_CONTACT
from manager.instances import create_instance_dir, fetch_bot_info, setup_instance, start_instance
from manager.storage import get_bots, get_user, is_admin, save_data, token_taken
from manager.subscriptions import days_left, is_active, pending_days

logger = logging.getLogger(__name__)

TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]{35,}$")

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)


@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id

    if is_admin(user_id):
        await message.answer(ui.ADMIN_HELP, parse_mode="HTML")
        return

    pending = pending_days(user_id)
    if pending > 0:
        await message.answer(
            ui.welcome(pending),
            reply_markup=ui.choice_keyboard(user_id, pending),
            parse_mode="HTML"
        )
        return

    bots = get_bots(user_id)
    if not bots:
        await message.answer(ui.no_subscription(), parse_mode="HTML")
        return

    lines = ["<b>Your bots:</b>\n"] + ui.bot_lines(bots)
    if not any(is_active(b) for b in bots):
        lines.append(f"\nContact {SUPPORT_CONTACT} to renew")

    await message.answer("\n".join(lines), reply_markup=ui.my_bots_keyboard(), parse_mode="HTML")


async def show_status(message: Message, user_id: int):
    pending = pending_days(user_id)
    if pending > 0:
        await message.answer(
            ui.welcome(pending),
            reply_markup=ui.choice_keyboard(user_id, pending),
            parse_mode="HTML"
        )
        return

    bots = get_bots(user_id)
    if not bots:
        await message.answer(ui.no_subscription(), parse_mode="HTML")
        return

    lines = ["<b>Your bots:</b>\n"]
    for bot_info in bots:
        status = f"{days_left(bot_info)}d left" if is_active(bot_info) else "expired"
        lines.append(f"- @{bot_info.get('bot_username', '???')} - {status}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message()
async def handle_message(message: Message):
    user_id = message.from_user.id
    if message.text and message.text.startswith("/"):
        return

    record = get_user(user_id)
    awaiting = record.get("awaiting_token")

    if not awaiting and not is_admin(user_id):
        await show_status(message, user_id)
        return

    token = (message.text or "").strip()
    if not TOKEN_RE.match(token):
        await message.answer(
            "<b>That doesn't look like a bot token</b>\n\n"
            "It should look like:\n" + ui.TOKEN_EXAMPLE,
            parse_mode="HTML"
        )
        return

    days = awaiting if awaiting else record.get("pending_days", 0)
    if days <= 0 and not is_admin(user_id):
        await message.answer("No pending subscription days available.")
        return

    await message.answer("Checking the token...")

    bot_info = await fetch_bot_info(token)
    if not bot_info:
        await message.answer(
            "<b>That token doesn't work</b>\n\n"
            "Double check you copied it correctly.",
            parse_mode="HTML"
        )
        return

    if token_taken(token, user_id):
        await message.answer("<b>This token is already used by another account</b>", parse_mode="HTML")
        return

    await message.answer("Creating your bot...")

    try:
        instance_dir = create_instance_dir(user_id)
        setup_instance(instance_dir, token, user_id)

        record["bots"].append({
            "bot_token": token,
            "bot_username": bot_info["username"],
            "instance_dir": instance_dir,
            "expires": (datetime.now() + timedelta(days=days)).isoformat(),
        })

        if awaiting:
            record["awaiting_token"] = None
            record["pending_days"] = max(0, record.get("pending_days", 0) - days)
        elif not is_admin(user_id):
            record["pending_days"] = 0

        record.pop("admin_create", None)
        save_data()
        start_instance(instance_dir)

        await message.answer(
            f"<b>Bot \"{bot_info['first_name']}\" is ready</b>\n\n"
            f"Subscription active for {days} days.\n"
            f"Use @{bot_info['username']} to start multiposting.",
            reply_markup=ui.bot_keyboard(bot_info["username"]),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"failed to create instance: {e}")
        await message.answer(
            "<b>Could not create the bot</b>\n\n"
            f"Contact {SUPPORT_CONTACT}",
            parse_mode="HTML"
        )
