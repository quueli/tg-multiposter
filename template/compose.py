import asyncio
import re
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from access import denied, is_owner
from scheduler import schedule_post
from sender import send_one
from storage import data, save_data

ALBUM_WAIT = 1.0

# in memory only, a restart drops whatever was waiting for a button press
albums = {}
drafts = {}
awaiting_time = {}

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)


def confirm_keyboard(key):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Send now", callback_data=f"send_{key}"),
            InlineKeyboardButton(text="Schedule", callback_data=f"schedule_{key}"),
        ],
        [InlineKeyboardButton(text="Cancel", callback_data=f"cancel_{key}")],
    ])


def parse_when(text):
    text = text.strip().lower()
    m = re.match(r"^in (\d+)\s*(m|min|h|hour)s?$", text)
    if m:
        amount, unit = int(m.group(1)), m.group(2)
        delta = timedelta(hours=amount) if unit in ("h", "hour") else timedelta(minutes=amount)
        return datetime.now() + delta
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def media_item(message: Message, with_caption=True):
    caption = message.caption if with_caption else None
    entities = message.caption_entities if with_caption else None

    if message.photo:
        return {"type": "photo", "file_id": message.photo[-1].file_id,
                "caption": caption, "caption_entities": entities}
    if message.video:
        return {"type": "video", "file_id": message.video.file_id,
                "caption": caption, "caption_entities": entities}
    if message.document:
        return {"type": "document", "file_id": message.document.file_id,
                "caption": caption, "caption_entities": entities}
    if message.audio:
        return {"type": "audio", "file_id": message.audio.file_id,
                "caption": caption, "caption_entities": entities}
    if message.voice:
        return {"type": "voice", "file_id": message.voice.file_id,
                "caption": caption, "caption_entities": entities}
    if message.video_note:
        return {"type": "video_note", "file_id": message.video_note.file_id,
                "caption": None, "caption_entities": None}
    if message.sticker:
        return {"type": "sticker", "file_id": message.sticker.file_id,
                "caption": None, "caption_entities": None}
    return None


async def collect_album(bot: Bot, album_id: str, user_id: int):
    await asyncio.sleep(ALBUM_WAIT)  # album items arrive as separate messages a few ms apart

    messages = sorted(albums.pop(album_id, []), key=lambda m: m.message_id)
    if not messages:
        return

    first = messages[0]
    items = []
    for i, msg in enumerate(messages):
        item = media_item(msg, with_caption=i == 0)
        if item:
            items.append(item)

    drafts[user_id] = {
        "key": first.message_id,
        "media_list": items,
        "text": first.caption,
        "text_entities": first.caption_entities,
        "is_media_group": True,
    }
    await send_preview(bot, first.chat.id, user_id, items, first.caption, True, first.caption_entities)


async def send_preview(bot: Bot, chat_id, user_id, media_list=None, text=None,
                       is_media_group=False, entities=None):
    groups = len(data["groups"])
    if not groups:
        await bot.send_message(
            chat_id,
            "This bot isn't registered in any group yet.\n\n"
            "Add it to a group and run /register there."
        )
        return

    await send_one(bot, chat_id, media_list or [], text, entities, is_media_group)

    await bot.send_message(
        chat_id,
        f"<b>Send this to {groups} chats?</b>",
        reply_markup=confirm_keyboard(drafts.get(user_id, {}).get("key", 0)),
        parse_mode="HTML"
    )


@router.message()
async def handle_private_message(message: Message, bot: Bot):
    user_id = message.from_user.id

    if not is_owner(user_id):
        await message.answer(denied(), parse_mode="HTML")
        return

    if message.text and message.text.startswith("/"):
        return

    if user_id in awaiting_time:
        await take_schedule_time(message, user_id)
        return

    if message.media_group_id:
        album_id = message.media_group_id
        if album_id not in albums:
            albums[album_id] = []
            asyncio.create_task(collect_album(bot, album_id, user_id))
        albums[album_id].append(message)
        return

    item = media_item(message)
    text = message.text or message.caption
    entities = message.entities or message.caption_entities

    drafts[user_id] = {
        "key": message.message_id,
        "media_list": [item] if item else [],
        "text": text,
        "text_entities": entities,
        "is_media_group": False,
    }

    await send_preview(bot, message.chat.id, user_id, [item] if item else [], text, False, entities)


async def take_schedule_time(message: Message, user_id: int):
    when = parse_when(message.text or "")
    if not when:
        await message.answer("Didn't get that. Reply with 'in 30m', 'in 2h', or 'YYYY-MM-DD HH:MM'.")
        return

    draft = drafts.pop(user_id, None)
    pin = awaiting_time.pop(user_id)
    if not draft:
        await message.answer("This message is gone, send a new one.")
        return

    schedule_post(data, dict(draft, pin=pin), send_at=when, owner_chat_id=message.chat.id)
    save_data()

    await message.answer(f"Scheduled for {when.strftime('%Y-%m-%d %H:%M')}.")
