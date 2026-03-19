from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from manager import ui
from manager.config import SUPPORT_CONTACT
from manager.instances import start_instance
from manager.storage import get_bots, get_user, is_admin, save_data
from manager.subscriptions import days_left, extend, is_active, pending_days, set_pending

router = Router()


@router.callback_query(F.data.startswith("extend_"))
async def on_extend(callback: CallbackQuery):
    _, index, days = callback.data.split("_")
    bot_index, days = int(index), int(days)

    bots = get_bots(callback.from_user.id)
    if bot_index >= len(bots):
        await callback.answer("Bot not found", show_alert=True)
        return

    bot_info = bots[bot_index]
    current = days_left(bot_info)

    await callback.message.edit_text(
        f"<b>Extend @{bot_info.get('bot_username', '???')}</b>\n\n"
        f"Current: {current} days left\n"
        f"Adding: +{days} days\n"
        f"New total: {current + days} days\n\n"
        f"Confirm?",
        reply_markup=ui.confirm_keyboard("extend", f"{bot_index}_{days}"),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("newbot_"))
async def on_newbot(callback: CallbackQuery):
    days = int(callback.data.split("_")[1])

    await callback.message.edit_text(
        f"<b>Create a new bot</b>\n\n"
        f"The new bot will get: {days} days\n\n"
        f"Confirm?",
        reply_markup=ui.confirm_keyboard("newbot", str(days)),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_extend_"))
async def on_confirm_extend(callback: CallbackQuery):
    user_id = callback.from_user.id
    index, days = callback.data.replace("confirm_extend_", "").split("_")
    bot_index, days = int(index), int(days)

    pending = pending_days(user_id)
    if pending < days:
        await callback.answer("Not enough pending days", show_alert=True)
        return

    if not extend(user_id, bot_index, days):
        await callback.answer("Could not extend the subscription", show_alert=True)
        return

    set_pending(user_id, pending - days)
    bot_info = get_bots(user_id)[bot_index]
    username = bot_info.get("bot_username", "???")

    if bot_info.get("instance_dir"):
        start_instance(bot_info["instance_dir"])

    await callback.message.edit_text(
        f"<b>@{username} extended</b>\n\n"
        f"Subscription now active for {days_left(bot_info)} more days.",
        reply_markup=ui.bot_keyboard(username),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_newbot_"))
async def on_confirm_newbot(callback: CallbackQuery):
    user_id = callback.from_user.id
    days = int(callback.data.replace("confirm_newbot_", ""))

    if pending_days(user_id) < days and not is_admin(user_id):
        await callback.answer("Not enough pending days", show_alert=True)
        return

    get_user(user_id)["awaiting_token"] = days
    save_data()

    await callback.message.edit_text(ui.token_prompt(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "cancel_action")
async def on_cancel(callback: CallbackQuery):
    user_id = callback.from_user.id
    pending = pending_days(user_id)

    if pending > 0:
        await callback.message.edit_text(
            ui.welcome(pending),
            reply_markup=ui.choice_keyboard(user_id, pending),
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text("Cancelled.")

    await callback.answer("Cancelled")


@router.callback_query(F.data == "my_bots")
async def on_my_bots(callback: CallbackQuery):
    user_id = callback.from_user.id
    bots = get_bots(user_id)

    if not bots:
        await callback.message.edit_text(
            "You don't have any bots yet.\n\n"
            f"Contact {SUPPORT_CONTACT} to get a subscription.",
            parse_mode="HTML"
        )
        await callback.answer()
        return

    lines = ["<b>Your bots:</b>\n"] + ui.bot_lines(bots)
    buttons = []
    for bot_info in bots:
        if is_active(bot_info):
            username = bot_info.get("bot_username", "???")
            buttons.append([InlineKeyboardButton(text=f"@{username}", url=f"https://t.me/{username}")])

    pending = pending_days(user_id)
    if pending > 0:
        lines.append(f"\nPending, not yet assigned: {pending} days")
        buttons.append([InlineKeyboardButton(
            text="Assign pending days",
            callback_data=f"distribute_{pending}"
        )])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await callback.message.edit_text("\n".join(lines), reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("distribute_"))
async def on_distribute(callback: CallbackQuery):
    days = int(callback.data.split("_")[1])

    await callback.message.edit_text(
        ui.welcome(days),
        reply_markup=ui.choice_keyboard(callback.from_user.id, days),
        parse_mode="HTML"
    )
    await callback.answer()
