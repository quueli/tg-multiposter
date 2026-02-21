import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from access import is_owner
from compose import drafts
from sender import multipost
from storage import data, drop_groups

logger = logging.getLogger(__name__)

router = Router()


def pin_keyboard(key):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Yes, pin it", callback_data=f"pin_yes_{key}"),
        InlineKeyboardButton(text="No, just send", callback_data=f"pin_no_{key}"),
    ]])


async def has_draft(callback: CallbackQuery) -> bool:
    if not is_owner(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return False
    if callback.from_user.id not in drafts:
        await callback.answer("This message is gone, send a new one.", show_alert=True)
        return False
    return True


@router.callback_query(F.data.startswith("send_"))
async def on_send(callback: CallbackQuery):
    if not await has_draft(callback):
        return

    await callback.message.edit_text(
        "Pin the message in the groups too?\n\n"
        "Make sure the bot is an admin with pin rights there.",
        reply_markup=pin_keyboard(callback.data.split("_", 1)[1])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pin_yes_"))
async def on_pin_yes(callback: CallbackQuery, bot: Bot):
    await deliver(callback, bot, pin=True)


@router.callback_query(F.data.startswith("pin_no_"))
async def on_pin_no(callback: CallbackQuery, bot: Bot):
    await deliver(callback, bot, pin=False)


@router.callback_query(F.data.startswith("cancel_"))
async def on_cancel(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not is_owner(user_id):
        await callback.answer("Access denied", show_alert=True)
        return

    drafts.pop(user_id, None)
    await callback.message.edit_text("Cancelled.")
    await callback.answer("Cancelled")


async def deliver(callback: CallbackQuery, bot: Bot, pin: bool):
    if not await has_draft(callback):
        return

    draft = drafts.pop(callback.from_user.id)
    total = len(data["groups"])
    await callback.message.edit_text(f"Sending... (0/{total})")

    async def report(done, count):
        try:
            await callback.message.edit_text(f"Sending... ({done}/{count})")
        except Exception:
            pass  # an edit with the same text comes back as an error

    result = await multipost(
        bot, data["groups"],
        media_list=draft.get("media_list"),
        text=draft.get("text"),
        text_entities=draft.get("text_entities"),
        is_media_group=draft.get("is_media_group", False),
        pin=pin,
        on_progress=report,
    )

    if result["removed_ids"]:
        drop_groups(set(result["removed_ids"]))
        logger.info(f"dropped {len(result['removed_ids'])} unreachable groups")

    text = f"Sent to {result['success']} of {result['total']} chats."
    if pin:
        pinned = result["success"] - result["pin_errors"]
        text += f"\nPinned: {pinned}"
        if result["pin_errors"]:
            text += f" ({result['pin_errors']} could not be pinned)"
    if result["errors"]:
        text += f"\nErrors: {result['errors']}"
    if result["removed_ids"]:
        text += f"\nDropped unreachable chats: {len(result['removed_ids'])}"

    await callback.message.edit_text(text)
    await callback.answer("Done")
