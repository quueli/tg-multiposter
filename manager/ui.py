from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from manager.config import SUBSCRIPTION_PERIOD, SUBSCRIPTION_PRICE, SUPPORT_CONTACT
from manager.storage import get_bots
from manager.subscriptions import days_left, is_active

ADMIN_HELP = (
    "<b>Admin panel</b>\n\n"
    "Commands:\n"
    "<code>/subscribe ID DAYS</code> - grant a subscription\n"
    "<code>/info ID</code> - info about a user\n"
    "<code>/list</code> - list users\n"
    "<code>/create</code> - create a bot for yourself"
)

TOKEN_EXAMPLE = "<code>1234567890:ABC-DEF1234ghIkl-zyx57W2v1u123ew11</code>"


def no_subscription():
    return (
        "<b>You don't have an active subscription</b>\n\n"
        f"Contact {SUPPORT_CONTACT} to get one.\n"
        f"{SUBSCRIPTION_PERIOD} - {SUBSCRIPTION_PRICE}"
    )


def welcome(days):
    return (
        f"<b>You've been given {days} days of subscription</b>\n\n"
        "Pick an action:\n"
        "- <b>Extend a bot</b> - add these days to a bot you already have\n"
        "- <b>Create a new one</b> - spin up a new bot for multiposting"
    )


def token_prompt():
    return (
        "<b>Create a new bot</b>\n\n"
        "1. Open @BotFather\n"
        "2. Send /newbot\n"
        "3. Pick a name\n"
        "4. Pick a username (must end in 'bot')\n"
        "5. Copy the token and send it here\n\n"
        "The token looks like:\n" + TOKEN_EXAMPLE
    )


def bot_lines(bots):
    lines = []
    for bot_info in bots:
        username = bot_info.get("bot_username", "???")
        if is_active(bot_info):
            lines.append(f"@{username} - {days_left(bot_info)} days left")
        else:
            lines.append(f"@{username} - subscription expired")
    return lines


def choice_keyboard(user_id, days):
    rows = []
    for i, bot_info in enumerate(get_bots(user_id)):
        username = bot_info.get("bot_username", "???")
        status = f"{days_left(bot_info)}d left" if is_active(bot_info) else "expired"
        rows.append([InlineKeyboardButton(
            text=f"Extend @{username} ({status})",
            callback_data=f"extend_{i}_{days}"
        )])

    rows.append([InlineKeyboardButton(text="Create a new bot", callback_data=f"newbot_{days}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_keyboard(action, payload):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Confirm", callback_data=f"confirm_{action}_{payload}"),
        InlineKeyboardButton(text="Cancel", callback_data="cancel_action"),
    ]])


def my_bots_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="My bots", callback_data="my_bots")]
    ])


def bot_keyboard(username):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Open the bot", url=f"https://t.me/{username}")],
        [InlineKeyboardButton(text="My bots", callback_data="my_bots")],
    ])
