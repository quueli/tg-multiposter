import asyncio
import json
import logging
import os
from typing import Dict, List

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import BOT_TOKEN, DATA_FILE, MAIN_BOT, OWNER_ID
from sender import build_input_media, multipost

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

data = {
    "groups": [],
}

media_group_data: Dict[str, Dict] = {}
pending_messages: Dict[int, Dict] = {}


def load_data():
    global data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                data["groups"] = loaded.get("groups", [])
        except Exception as e:
            logger.error(f"failed to load data: {e}")


def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def get_access_denied_message() -> str:
    return (
        f"<b>Access denied</b>\n\n"
        f"This bot belongs to someone else.\n\n"
        f"To get your own multiposting bot, talk to {MAIN_BOT}"
    )


def is_group_chat(chat_type) -> bool:
    return chat_type in (ChatType.GROUP, ChatType.SUPERGROUP)


def register_group(chat_id: int, chat_title: str) -> bool:
    if not any(g["id"] == chat_id for g in data["groups"]):
        data["groups"].append({"id": chat_id, "title": chat_title or "Untitled"})
        save_data()
        logger.info(f"registered group {chat_title} ({chat_id})")
        return True
    return False


def get_confirmation_keyboard(message_id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Send now", callback_data=f"send_{message_id}"),
            InlineKeyboardButton(text="Cancel", callback_data=f"cancel_{message_id}"),
        ]
    ])


def get_pin_keyboard(message_id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Yes, pin it", callback_data=f"pin_yes_{message_id}"),
            InlineKeyboardButton(text="No, just send", callback_data=f"pin_no_{message_id}"),
        ]
    ])


def merge_media_group(messages: List[Message]) -> Dict:
    caption = None
    caption_entities = None
    media_list = []

    for i, msg in enumerate(messages):
        item_caption = msg.caption if i == 0 else None
        item_entities = msg.caption_entities if i == 0 else None
        if i == 0 and msg.caption:
            caption = msg.caption
            caption_entities = msg.caption_entities

        if msg.photo:
            media_list.append({"type": "photo", "file_id": msg.photo[-1].file_id,
                               "caption": item_caption, "caption_entities": item_entities})
        elif msg.video:
            media_list.append({"type": "video", "file_id": msg.video.file_id,
                               "caption": item_caption, "caption_entities": item_entities})
        elif msg.document:
            media_list.append({"type": "document", "file_id": msg.document.file_id,
                               "caption": item_caption, "caption_entities": item_entities})
        elif msg.audio:
            media_list.append({"type": "audio", "file_id": msg.audio.file_id,
                               "caption": item_caption, "caption_entities": item_entities})

    return {"media_list": media_list, "text": caption, "text_entities": caption_entities}


@router.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type != ChatType.PRIVATE:
        return

    if not is_owner(message.from_user.id):
        await message.answer(get_access_denied_message(), parse_mode="HTML")
        return

    groups_count = len(data["groups"])
    await message.answer(
        f"Hi. I multipost to {groups_count} groups.\n\n"
        f"Send me a message (text, photo, video, documents, etc.) and I'll fan it out.\n\n"
        f"Commands:\n"
        f"/groups - list groups\n"
        f"/register - run this inside a group to register it"
    )


@router.message(Command("register"))
async def cmd_register(message: Message):
    if not is_group_chat(message.chat.type):
        if not is_owner(message.from_user.id):
            await message.answer(get_access_denied_message(), parse_mode="HTML")
            return
        await message.answer("This command only works inside a group.")
        return

    chat_id = message.chat.id
    chat_title = message.chat.title

    if register_group(chat_id, chat_title):
        await message.answer(f'Group "{chat_title}" registered.')
    else:
        await message.answer(f'"{chat_title}" is already registered.')


@router.message(Command("groups"))
async def cmd_groups(message: Message):
    if message.chat.type != ChatType.PRIVATE:
        return

    if not is_owner(message.from_user.id):
        await message.answer(get_access_denied_message(), parse_mode="HTML")
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
    new_status = update.new_chat_member.status

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    if new_status in ("member", "administrator"):
        register_group(chat.id, chat.title)
    elif new_status in ("left", "kicked"):
        data["groups"] = [g for g in data["groups"] if g["id"] != chat.id]
        save_data()
        logger.info(f"removed from group {chat.title} ({chat.id})")


@router.message(F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]))
async def handle_group_message(message: Message):
    register_group(message.chat.id, message.chat.title)


async def collect_media_group(media_group_id: str, user_id: int, timeout: float = 1.0):
    await asyncio.sleep(timeout)  # album items arrive as separate messages a few ms apart

    if media_group_id not in media_group_data:
        return

    group_data = media_group_data.pop(media_group_id)
    messages = sorted(group_data["messages"], key=lambda m: m.message_id)
    if not messages:
        return

    merged = merge_media_group(messages)
    first_msg = messages[0]

    pending_messages[user_id] = {
        "key": first_msg.message_id,
        "media_list": merged["media_list"],
        "text": merged["text"],
        "text_entities": merged["text_entities"],
        "is_media_group": True,
    }

    await send_preview(first_msg.chat.id, user_id, merged["media_list"], merged["text"], True,
                       merged["text_entities"])


async def send_preview(chat_id: int, user_id: int, media_list=None, text=None,
                       is_media_group: bool = False, entities=None):
    groups_count = len(data["groups"])

    if groups_count == 0:
        await bot.send_message(
            chat_id,
            "This bot isn't registered in any group yet.\n\n"
            "Add it to a group and run /register there."
        )
        return

    if is_media_group and media_list:
        input_media = build_input_media(media_list)
        if input_media:
            await bot.send_media_group(chat_id, input_media)
    elif media_list and len(media_list) == 1:
        item = media_list[0]
        item_entities = item.get("caption_entities") or entities
        kind = item["type"]
        if kind == "photo":
            await bot.send_photo(chat_id, item["file_id"], caption=text, caption_entities=item_entities)
        elif kind == "video":
            await bot.send_video(chat_id, item["file_id"], caption=text, caption_entities=item_entities)
        elif kind == "document":
            await bot.send_document(chat_id, item["file_id"], caption=text, caption_entities=item_entities)
        elif kind == "audio":
            await bot.send_audio(chat_id, item["file_id"], caption=text, caption_entities=item_entities)
        elif kind == "voice":
            await bot.send_voice(chat_id, item["file_id"], caption=text, caption_entities=item_entities)
        elif kind == "video_note":
            await bot.send_video_note(chat_id, item["file_id"])
        elif kind == "sticker":
            await bot.send_sticker(chat_id, item["file_id"])
    elif text:
        await bot.send_message(chat_id, text, entities=entities)

    pending_key = pending_messages.get(user_id, {}).get("key", 0)
    await bot.send_message(
        chat_id,
        f"<b>Send this to {groups_count} chats?</b>",
        reply_markup=get_confirmation_keyboard(pending_key),
        parse_mode="HTML"
    )


@router.message(F.chat.type == ChatType.PRIVATE)
async def handle_private_message(message: Message):
    user_id = message.from_user.id

    if not is_owner(user_id):
        await message.answer(get_access_denied_message(), parse_mode="HTML")
        return

    if message.text and message.text.startswith("/"):
        return

    if message.media_group_id:
        mg_id = message.media_group_id

        if mg_id not in media_group_data:
            media_group_data[mg_id] = {"messages": [], "user_id": user_id}
            asyncio.create_task(collect_media_group(mg_id, user_id))

        media_group_data[mg_id]["messages"].append(message)
        return

    media_list = []
    text = message.text or message.caption
    entities = message.entities or message.caption_entities

    if message.photo:
        media_list.append({"type": "photo", "file_id": message.photo[-1].file_id,
                           "caption": message.caption, "caption_entities": message.caption_entities})
    elif message.video:
        media_list.append({"type": "video", "file_id": message.video.file_id,
                           "caption": message.caption, "caption_entities": message.caption_entities})
    elif message.document:
        media_list.append({"type": "document", "file_id": message.document.file_id,
                           "caption": message.caption, "caption_entities": message.caption_entities})
    elif message.audio:
        media_list.append({"type": "audio", "file_id": message.audio.file_id,
                           "caption": message.caption, "caption_entities": message.caption_entities})
    elif message.voice:
        media_list.append({"type": "voice", "file_id": message.voice.file_id,
                           "caption": message.caption, "caption_entities": message.caption_entities})
    elif message.video_note:
        media_list.append({"type": "video_note", "file_id": message.video_note.file_id,
                           "caption": None, "caption_entities": None})
    elif message.sticker:
        media_list.append({"type": "sticker", "file_id": message.sticker.file_id,
                           "caption": None, "caption_entities": None})

    pending_messages[user_id] = {
        "key": message.message_id,
        "media_list": media_list,
        "text": text,
        "text_entities": entities,
        "is_media_group": False,
    }

    await send_preview(message.chat.id, user_id, media_list, text, False, entities)


@router.callback_query(F.data.startswith("send_"))
async def callback_send(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not is_owner(user_id):
        await callback.answer("Access denied", show_alert=True)
        return
    if user_id not in pending_messages:
        await callback.answer("This message is gone, send a new one.", show_alert=True)
        return

    message_id = callback.data.split("_", 1)[1]
    await callback.message.edit_text(
        "Pin the message in the groups too?\n\n"
        "Make sure the bot is an admin with pin rights there.",
        reply_markup=get_pin_keyboard(message_id)
    )
    await callback.answer()


async def deliver_now(callback: CallbackQuery, pin: bool):
    user_id = callback.from_user.id
    if not is_owner(user_id):
        await callback.answer("Access denied", show_alert=True)
        return
    if user_id not in pending_messages:
        await callback.answer("This message is gone, send a new one.", show_alert=True)
        return

    payload = pending_messages.pop(user_id)
    total = len(data["groups"])
    await callback.message.edit_text(f"Sending... (0/{total})")

    async def report_progress(done, total_count):
        try:
            await callback.message.edit_text(f"Sending... ({done}/{total_count})")
        except Exception:
            pass

    result = await multipost(
        bot, data["groups"],
        media_list=payload.get("media_list"),
        text=payload.get("text"),
        text_entities=payload.get("text_entities"),
        is_media_group=payload.get("is_media_group", False),
        pin=pin,
        on_progress=report_progress,
    )

    if result["removed_ids"]:
        data["groups"] = [g for g in data["groups"] if g["id"] not in result["removed_ids"]]
        save_data()
        logger.info(f"dropped {len(result['removed_ids'])} unreachable groups")

    text = f"Sent to {result['success']} of {result['total']} chats."
    if pin:
        pinned = result["success"] - result["pin_errors"]
        text += f"\nPinned: {pinned}"
        if result["pin_errors"]:
            text += f" ({result['pin_errors']} could not be pinned)"
    if result["errors"]:
        text += f"\nErrors: {result['errors']}"

    await callback.message.edit_text(text)
    await callback.answer("Done")


@router.callback_query(F.data.startswith("pin_yes_"))
async def callback_pin_yes(callback: CallbackQuery):
    await deliver_now(callback, pin=True)


@router.callback_query(F.data.startswith("pin_no_"))
async def callback_pin_no(callback: CallbackQuery):
    await deliver_now(callback, pin=False)


@router.callback_query(F.data.startswith("cancel_"))
async def callback_cancel(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not is_owner(user_id):
        await callback.answer("Access denied", show_alert=True)
        return

    pending_messages.pop(user_id, None)
    await callback.message.edit_text("Cancelled.")
    await callback.answer("Cancelled")


async def main():
    load_data()

    logger.info(f"bot running for owner {OWNER_ID}")
    logger.info(f"groups: {len(data['groups'])}")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
