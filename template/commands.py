import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message

from access import denied, is_owner
from storage import data, drop_groups, register_group

logger = logging.getLogger(__name__)

GROUP_TYPES = (ChatType.GROUP, ChatType.SUPERGROUP)

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type != ChatType.PRIVATE:
        return

    if not is_owner(message.from_user.id):
        await message.answer(denied(), parse_mode="HTML")
        return

    await message.answer(
        f"Hi. I multipost to {len(data['groups'])} groups.\n\n"
        f"Send me a message (text, photo, video, documents, etc.) and I'll fan it out.\n\n"
        f"Commands:\n"
        f"/groups - list groups\n"
        f"/register - run this inside a group to register it"
    )


@router.message(Command("register"))
async def cmd_register(message: Message):
    if message.chat.type not in GROUP_TYPES:
        if not is_owner(message.from_user.id):
            await message.answer(denied(), parse_mode="HTML")
            return
        await message.answer("This command only works inside a group.")
        return

    if register_group(message.chat.id, message.chat.title):
        await message.answer(f'Group "{message.chat.title}" registered.')
    else:
        await message.answer(f'"{message.chat.title}" is already registered.')


@router.message(Command("groups"))
async def cmd_groups(message: Message):
    if message.chat.type != ChatType.PRIVATE:
        return

    if not is_owner(message.from_user.id):
        await message.answer(denied(), parse_mode="HTML")
        return

    if not data["groups"]:
        await message.answer(
            "Not registered in any group yet.\n\n"
            "Add the bot to a group and run /register there."
        )
        return

    lines = [f"- {g['title']} (id: {g['id']})" for g in data["groups"]]
    await message.answer(
        f"<b>Groups ({len(data['groups'])}):</b>\n\n" + "\n".join(lines),
        parse_mode="HTML"
    )


@router.my_chat_member()
async def on_chat_member_update(update):
    chat = update.chat
    if chat.type not in GROUP_TYPES:
        return

    status = update.new_chat_member.status
    if status in ("member", "administrator"):
        register_group(chat.id, chat.title)
    elif status in ("left", "kicked"):
        drop_groups({chat.id})
        logger.info(f"removed from group {chat.title} ({chat.id})")


@router.message(F.chat.type.in_(GROUP_TYPES))
async def handle_group_message(message: Message):
    register_group(message.chat.id, message.chat.title)
