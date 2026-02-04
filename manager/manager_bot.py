import asyncio
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from manager.config import ADMINS, BOT_TOKEN, DATA_FILE, INSTANCES_DIR, SUPPORT_CONTACT, TEMPLATE_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# {
#   "users": {
#     "<user_id>": {
#       "pending_days": 0,       # days paid for but not yet assigned to a bot
#       "bots": [
#         {"bot_token": "...", "bot_username": "...", "instance_dir": "...", "expires": "<iso>"}
#       ]
#     }
#   }
# }
data = {
    "users": {}
}

running_processes: Dict[str, subprocess.Popen] = {}  # instance_dir -> process


def load_data():
    global data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if "subscriptions" in loaded:
                    data["users"] = migrate_old_format(loaded["subscriptions"])
                else:
                    data["users"] = {str(k): v for k, v in loaded.get("users", {}).items()}
        except Exception as e:
            logger.error(f"failed to load data: {e}")


def migrate_old_format(old_subs: dict) -> dict:
    # first version kept one bot per user with no list, flatten it into the new shape
    new_users = {}
    for user_id, info in old_subs.items():
        bots = []
        if info.get("bot_token"):
            bots.append({
                "bot_token": info["bot_token"],
                "bot_username": info.get("bot_username"),
                "instance_dir": info.get("instance_dir"),
                "expires": info.get("expires")
            })
        new_users[str(user_id)] = {
            "pending_days": 0,
            "bots": bots
        }
    return new_users


def save_data():
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def is_admin(user_id: int) -> bool:
    return user_id in ADMINS


def get_user_data(user_id: int) -> dict:
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {"pending_days": 0, "bots": []}
    return data["users"][uid]


def get_user_bots(user_id: int) -> List[dict]:
    return get_user_data(user_id).get("bots", [])


def get_pending_days(user_id: int) -> int:
    return get_user_data(user_id).get("pending_days", 0)


def set_pending_days(user_id: int, days: int):
    get_user_data(user_id)["pending_days"] = days
    save_data()


def add_pending_days(user_id: int, days: int):
    user_data = get_user_data(user_id)
    user_data["pending_days"] = user_data.get("pending_days", 0) + days
    save_data()


def bot_has_subscription(bot_info: dict) -> bool:
    expires = bot_info.get("expires")
    if not expires:
        return False
    return datetime.fromisoformat(expires) > datetime.now()


def get_bot_days_left(bot_info: dict) -> int:
    expires = bot_info.get("expires")
    if not expires:
        return 0
    delta = datetime.fromisoformat(expires) - datetime.now()
    return max(0, delta.days)


def extend_bot_subscription(user_id: int, bot_index: int, days: int) -> bool:
    user_data = get_user_data(user_id)
    bots = user_data.get("bots", [])

    if bot_index >= len(bots):
        return False

    bot_info = bots[bot_index]
    current_expires = bot_info.get("expires")

    if current_expires:
        current_date = datetime.fromisoformat(current_expires)
        base = current_date if current_date > datetime.now() else datetime.now()
    else:
        base = datetime.now()

    bot_info["expires"] = (base + timedelta(days=days)).isoformat()
    save_data()
    return True


def user_has_any_active_bot(user_id: int) -> bool:
    return any(bot_has_subscription(b) for b in get_user_bots(user_id))


async def get_bot_info(token: str) -> Optional[dict]:
    try:
        temp_bot = Bot(token=token)
        info = await temp_bot.get_me()
        await temp_bot.session.close()
        return {"username": info.username, "first_name": info.first_name}
    except Exception as e:
        logger.error(f"could not fetch bot info: {e}")
        return None


def create_instance_dir(user_id: int) -> str:
    random_hash = secrets.token_hex(4)
    dir_name = f"{user_id}_{random_hash}"
    instance_path = os.path.join(INSTANCES_DIR, dir_name)
    os.makedirs(instance_path, exist_ok=True)
    return instance_path


def setup_instance(instance_path: str, bot_token: str, owner_id: int):
    for item in os.listdir(TEMPLATE_DIR):
        src = os.path.join(TEMPLATE_DIR, item)
        dst = os.path.join(instance_path, item)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
        elif os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)

    env_path = os.path.join(instance_path, ".env")
    with open(env_path, 'w') as f:
        f.write(f"BOT_TOKEN={bot_token}\n")
        f.write(f"OWNER_ID={owner_id}\n")

    data_path = os.path.join(instance_path, "data.json")
    with open(data_path, 'w') as f:
        json.dump({"groups": []}, f)


def start_instance(instance_dir: str) -> bool:
    if not instance_dir or not os.path.exists(instance_dir):
        logger.error(f"instance dir does not exist: {instance_dir}")
        return False

    bot_script = os.path.join(instance_dir, "bot.py")
    if not os.path.exists(bot_script):
        logger.error(f"bot.py missing in {instance_dir}")
        return False

    if instance_dir in running_processes:
        proc = running_processes[instance_dir]
        if proc.poll() is None:
            return True

    try:
        log_file = os.path.join(instance_dir, "bot.log")
        log_handle = open(log_file, 'a', encoding='utf-8')

        proc = subprocess.Popen(
            [sys.executable, "-u", bot_script],
            cwd=instance_dir,
            stdout=log_handle,
            stderr=subprocess.STDOUT
        )
        running_processes[instance_dir] = proc
        logger.info(f"started instance {instance_dir}, pid {proc.pid}")
        return True
    except Exception as e:
        logger.error(f"failed to start instance: {e}")
        return False


def stop_instance(instance_dir: str) -> bool:
    if instance_dir not in running_processes:
        return False

    proc = running_processes[instance_dir]
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    except Exception as e:
        logger.error(f"failed to stop instance: {e}")
        return False

    del running_processes[instance_dir]
    logger.info(f"stopped instance {instance_dir}")
    return True


def get_no_subscription_message() -> str:
    return (
        f"<b>You don't have an active subscription</b>\n\n"
        f"Contact {SUPPORT_CONTACT} to get one."
    )


def get_welcome_message(days: int) -> str:
    return (
        f"<b>You've been given {days} days of subscription</b>\n\n"
        "Pick an action:\n"
        "- <b>Extend a bot</b> - add these days to a bot you already have\n"
        "- <b>Create a new one</b> - spin up a new bot for multiposting"
    )


def get_create_bot_message() -> str:
    return (
        "<b>Create a new bot</b>\n\n"
        "1. Open @BotFather\n"
        "2. Send /newbot\n"
        "3. Pick a name\n"
        "4. Pick a username (must end in 'bot')\n"
        "5. Copy the token and send it here\n\n"
        "The token looks like:\n"
        "<code>1234567890:ABC-DEF1234ghIkl-zyx57W2v1u123ew11</code>"
    )


def get_subscription_choice_keyboard(user_id: int, days: int) -> InlineKeyboardMarkup:
    buttons = []

    for i, bot_info in enumerate(get_user_bots(user_id)):
        username = bot_info.get("bot_username", "???")
        days_left = get_bot_days_left(bot_info)
        status = f"{days_left}d left" if bot_has_subscription(bot_info) else "expired"
        buttons.append([InlineKeyboardButton(
            text=f"Extend @{username} ({status})",
            callback_data=f"extend_{i}_{days}"
        )])

    buttons.append([InlineKeyboardButton(
        text="Create a new bot",
        callback_data=f"newbot_{days}"
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_confirm_keyboard(action: str, payload: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Confirm", callback_data=f"confirm_{action}_{payload}"),
            InlineKeyboardButton(text="Cancel", callback_data="cancel_action")
        ]
    ])


def get_bot_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Open the bot", url=f"https://t.me/{bot_username}")],
        [InlineKeyboardButton(text="My bots", callback_data="my_bots")]
    ])


@router.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id

    if is_admin(user_id):
        await message.answer(
            "<b>Admin panel</b>\n\n"
            "Commands:\n"
            "<code>/subscribe ID DAYS</code> - grant a subscription\n"
            "<code>/info ID</code> - info about a user\n"
            "<code>/list</code> - list users\n"
            "<code>/create</code> - create a bot for yourself",
            parse_mode="HTML"
        )
        return

    pending = get_pending_days(user_id)
    if pending > 0:
        await message.answer(
            get_welcome_message(pending),
            reply_markup=get_subscription_choice_keyboard(user_id, pending),
            parse_mode="HTML"
        )
        return

    bots = get_user_bots(user_id)
    if not bots:
        await message.answer(get_no_subscription_message(), parse_mode="HTML")
        return

    text_parts = ["<b>Your bots:</b>\n"]
    has_active = False

    for bot_info in bots:
        username = bot_info.get("bot_username", "???")
        days_left = get_bot_days_left(bot_info)
        if bot_has_subscription(bot_info):
            text_parts.append(f"@{username} - {days_left} days left")
            has_active = True
        else:
            text_parts.append(f"@{username} - subscription expired")

    if not has_active:
        text_parts.append(f"\nContact {SUPPORT_CONTACT} to renew")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="My bots", callback_data="my_bots")]
    ])

    await message.answer("\n".join(text_parts), reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message):
    if message.chat.type != ChatType.PRIVATE:
        return

    if not is_admin(message.from_user.id):
        await message.answer("This command is for admins only.")
        return

    args = message.text.split()
    if len(args) < 3:
        await message.answer("usage: /subscribe ID DAYS")
        return

    try:
        target_user_id = int(args[1])
        days = int(args[2])
    except ValueError:
        await message.answer("ID and DAYS must be numbers.")
        return

    if days <= 0:
        await message.answer("DAYS must be greater than 0.")
        return

    add_pending_days(target_user_id, days)
    total_pending = get_pending_days(target_user_id)

    await message.answer(
        f"Added {days} days of subscription to {target_user_id}.\n"
        f"Pending, not yet assigned to a bot: {total_pending} days"
    )

    try:
        await bot.send_message(
            target_user_id,
            get_welcome_message(total_pending),
            reply_markup=get_subscription_choice_keyboard(target_user_id, total_pending),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"could not notify {target_user_id}: {e}")
        await message.answer("Could not notify the user (they may not have started the bot).")


@router.message(Command("info"))
async def cmd_info(message: Message):
    if message.chat.type != ChatType.PRIVATE:
        return

    if not is_admin(message.from_user.id):
        await message.answer("This command is for admins only.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("usage: /info ID")
        return

    try:
        target_user_id = int(args[1])
    except ValueError:
        await message.answer("ID must be a number.")
        return

    user_data = data["users"].get(str(target_user_id))
    if not user_data:
        await message.answer(f"No such user: {target_user_id}")
        return

    pending = user_data.get("pending_days", 0)
    bots = user_data.get("bots", [])

    text_parts = [f"<b>User {target_user_id}</b>\n"]
    text_parts.append(f"Pending days: {pending}\n")
    text_parts.append(f"Bots: {len(bots)}\n")

    for i, bot_info in enumerate(bots):
        username = bot_info.get("bot_username", "???")
        days_left = get_bot_days_left(bot_info)
        status = "active" if bot_has_subscription(bot_info) else "expired"
        expires = bot_info.get("expires", "-")
        text_parts.append(f"\n[{status}] bot {i + 1}: @{username}")
        text_parts.append(f"   expires: {expires}")
        text_parts.append(f"   days left: {days_left}")

    await message.answer("\n".join(text_parts), parse_mode="HTML")


@router.message(Command("list"))
async def cmd_list(message: Message):
    if message.chat.type != ChatType.PRIVATE:
        return

    if not is_admin(message.from_user.id):
        await message.answer("This command is for admins only.")
        return

    if not data["users"]:
        await message.answer("No users yet.")
        return

    text_parts = ["<b>Users:</b>\n"]

    for user_id, user_data in data["users"].items():
        pending = user_data.get("pending_days", 0)
        bots = user_data.get("bots", [])
        active_bots = sum(1 for b in bots if bot_has_subscription(b))
        text_parts.append(f"- {user_id}: {len(bots)} bots ({active_bots} active), +{pending}d pending")

    await message.answer("\n".join(text_parts), parse_mode="HTML")


@router.message(Command("create"))
async def cmd_create(message: Message):
    # lets an admin spin up a bot without spending subscription days
    if message.chat.type != ChatType.PRIVATE:
        return

    if not is_admin(message.from_user.id):
        await message.answer("This command is for admins only.")
        return

    user_data = get_user_data(message.from_user.id)
    user_data["pending_days"] = 36500
    user_data["admin_create"] = True
    save_data()

    await message.answer(get_create_bot_message(), parse_mode="HTML")


@router.callback_query(F.data.startswith("extend_"))
async def callback_extend(callback: CallbackQuery):
    user_id = callback.from_user.id
    parts = callback.data.split("_")
    bot_index = int(parts[1])
    days = int(parts[2])

    bots = get_user_bots(user_id)
    if bot_index >= len(bots):
        await callback.answer("Bot not found", show_alert=True)
        return

    bot_info = bots[bot_index]
    username = bot_info.get("bot_username", "???")
    current_days = get_bot_days_left(bot_info)
    new_total = current_days + days

    await callback.message.edit_text(
        f"<b>Extend @{username}</b>\n\n"
        f"Current: {current_days} days left\n"
        f"Adding: +{days} days\n"
        f"New total: {new_total} days\n\n"
        f"Confirm?",
        reply_markup=get_confirm_keyboard("extend", f"{bot_index}_{days}"),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("newbot_"))
async def callback_newbot(callback: CallbackQuery):
    days = int(callback.data.split("_")[1])

    await callback.message.edit_text(
        f"<b>Create a new bot</b>\n\n"
        f"The new bot will get: {days} days\n\n"
        f"Confirm?",
        reply_markup=get_confirm_keyboard("newbot", str(days)),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_extend_"))
async def callback_confirm_extend(callback: CallbackQuery):
    user_id = callback.from_user.id
    parts = callback.data.replace("confirm_extend_", "").split("_")
    bot_index = int(parts[0])
    days = int(parts[1])

    pending = get_pending_days(user_id)
    if pending < days:
        await callback.answer("Not enough pending days", show_alert=True)
        return

    if extend_bot_subscription(user_id, bot_index, days):
        set_pending_days(user_id, pending - days)

        bots = get_user_bots(user_id)
        bot_info = bots[bot_index]
        username = bot_info.get("bot_username", "???")
        new_days = get_bot_days_left(bot_info)

        instance_dir = bot_info.get("instance_dir")
        if instance_dir:
            start_instance(instance_dir)

        await callback.message.edit_text(
            f"<b>@{username} extended</b>\n\n"
            f"Subscription now active for {new_days} more days.",
            reply_markup=get_bot_keyboard(username),
            parse_mode="HTML"
        )
    else:
        await callback.answer("Could not extend the subscription", show_alert=True)

    await callback.answer()


@router.callback_query(F.data.startswith("confirm_newbot_"))
async def callback_confirm_newbot(callback: CallbackQuery):
    user_id = callback.from_user.id
    days = int(callback.data.replace("confirm_newbot_", ""))

    pending = get_pending_days(user_id)
    if pending < days and not is_admin(user_id):
        await callback.answer("Not enough pending days", show_alert=True)
        return

    user_data = get_user_data(user_id)
    user_data["awaiting_token"] = days
    save_data()

    await callback.message.edit_text(get_create_bot_message(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "cancel_action")
async def callback_cancel_action(callback: CallbackQuery):
    user_id = callback.from_user.id
    pending = get_pending_days(user_id)

    if pending > 0:
        await callback.message.edit_text(
            get_welcome_message(pending),
            reply_markup=get_subscription_choice_keyboard(user_id, pending),
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text("Cancelled.")

    await callback.answer("Cancelled")


@router.callback_query(F.data == "my_bots")
async def callback_my_bots(callback: CallbackQuery):
    user_id = callback.from_user.id
    bots = get_user_bots(user_id)

    if not bots:
        await callback.message.edit_text(
            f"You don't have any bots yet.\n\n"
            f"Contact {SUPPORT_CONTACT} to get a subscription.",
            parse_mode="HTML"
        )
        await callback.answer()
        return

    text_parts = ["<b>Your bots:</b>\n"]
    buttons = []

    for bot_info in bots:
        username = bot_info.get("bot_username", "???")
        days_left = get_bot_days_left(bot_info)

        if bot_has_subscription(bot_info):
            text_parts.append(f"@{username} - {days_left} days left")
            buttons.append([InlineKeyboardButton(
                text=f"@{username}",
                url=f"https://t.me/{username}"
            )])
        else:
            text_parts.append(f"@{username} - subscription expired")

    pending = get_pending_days(user_id)
    if pending > 0:
        text_parts.append(f"\nPending, not yet assigned: {pending} days")
        buttons.append([InlineKeyboardButton(
            text="Assign pending days",
            callback_data=f"distribute_{pending}"
        )])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

    await callback.message.edit_text("\n".join(text_parts), reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("distribute_"))
async def callback_distribute(callback: CallbackQuery):
    user_id = callback.from_user.id
    days = int(callback.data.split("_")[1])

    await callback.message.edit_text(
        get_welcome_message(days),
        reply_markup=get_subscription_choice_keyboard(user_id, days),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(F.chat.type == ChatType.PRIVATE)
async def handle_message(message: Message):
    user_id = message.from_user.id

    if message.text and message.text.startswith("/"):
        return

    user_data = get_user_data(user_id)

    awaiting = user_data.get("awaiting_token")
    if not awaiting and not is_admin(user_id):
        pending = get_pending_days(user_id)
        if pending > 0:
            await message.answer(
                get_welcome_message(pending),
                reply_markup=get_subscription_choice_keyboard(user_id, pending),
                parse_mode="HTML"
            )
        else:
            await message.answer(get_no_subscription_message(), parse_mode="HTML")
        return

    text = message.text or ""
    token_pattern = r'^\d+:[A-Za-z0-9_-]{35,}$'

    if not re.match(token_pattern, text.strip()):
        await message.answer(
            "<b>That doesn't look like a bot token</b>\n\n"
            "It should look like:\n"
            "<code>1234567890:ABC-DEF1234ghIkl-zyx57W2v1u123ew11</code>",
            parse_mode="HTML"
        )
        return

    token = text.strip()
    days = awaiting if awaiting else user_data.get("pending_days", 0)

    if days <= 0 and not is_admin(user_id):
        await message.answer("No pending subscription days available.")
        return

    await message.answer("Checking the token...")

    bot_info = await get_bot_info(token)
    if not bot_info:
        await message.answer(
            "<b>That token doesn't work</b>\n\n"
            "Double check you copied it correctly.",
            parse_mode="HTML"
        )
        return

    bot_username = bot_info["username"]
    bot_name = bot_info["first_name"]

    # a token can only ever belong to one instance, otherwise two processes fight over the same bot
    for uid, udata in data["users"].items():
        for b in udata.get("bots", []):
            if b.get("bot_token") == token and int(uid) != user_id:
                await message.answer(
                    "<b>This token is already used by another account</b>",
                    parse_mode="HTML"
                )
                return

    await message.answer("Creating your bot...")

    try:
        instance_dir = create_instance_dir(user_id)
        setup_instance(instance_dir, token, user_id)

        expires = datetime.now() + timedelta(days=days)
        new_bot = {
            "bot_token": token,
            "bot_username": bot_username,
            "instance_dir": instance_dir,
            "expires": expires.isoformat()
        }
        user_data["bots"].append(new_bot)

        if awaiting:
            user_data["awaiting_token"] = None
            current_pending = user_data.get("pending_days", 0)
            user_data["pending_days"] = max(0, current_pending - days)
        elif not is_admin(user_id):
            user_data["pending_days"] = 0

        if "admin_create" in user_data:
            del user_data["admin_create"]

        save_data()
        start_instance(instance_dir)

        await message.answer(
            f"<b>Bot \"{bot_name}\" is ready</b>\n\n"
            f"Subscription active for {days} days.\n"
            f"Use @{bot_username} to start multiposting.",
            reply_markup=get_bot_keyboard(bot_username),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"failed to create instance: {e}")
        await message.answer(
            f"<b>Could not create the bot</b>\n\n"
            f"Contact {SUPPORT_CONTACT}",
            parse_mode="HTML"
        )


async def check_subscriptions():
    notified = set()

    while True:
        await asyncio.sleep(60)

        for user_id, user_data in list(data["users"].items()):
            if is_admin(int(user_id)):
                continue

            for bot_info in user_data.get("bots", []):
                instance_dir = bot_info.get("instance_dir")
                if not instance_dir:
                    continue

                bot_key = f"{user_id}_{bot_info.get('bot_username')}"

                if bot_has_subscription(bot_info):
                    notified.discard(bot_key)
                    if instance_dir not in running_processes:
                        start_instance(instance_dir)
                else:
                    if instance_dir in running_processes:
                        stop_instance(instance_dir)

                    if bot_key not in notified:
                        try:
                            username = bot_info.get("bot_username", "")
                            await bot.send_message(
                                int(user_id),
                                f"<b>Subscription for @{username} has expired</b>\n\n"
                                f"The bot has been stopped.\n"
                                f"Contact {SUPPORT_CONTACT} to renew.",
                                parse_mode="HTML"
                            )
                            notified.add(bot_key)
                        except Exception as e:
                            logger.warning(f"could not notify {user_id}: {e}")


async def startup():
    load_data()
    os.makedirs(INSTANCES_DIR, exist_ok=True)
    os.makedirs(TEMPLATE_DIR, exist_ok=True)

    for user_id, user_data in data["users"].items():
        for bot_info in user_data.get("bots", []):
            if bot_has_subscription(bot_info):
                instance_dir = bot_info.get("instance_dir")
                if instance_dir:
                    start_instance(instance_dir)

    logger.info(f"started {len(running_processes)} instances")


async def shutdown():
    for instance_dir in list(running_processes.keys()):
        stop_instance(instance_dir)


async def main():
    await startup()
    asyncio.create_task(check_subscriptions())

    logger.info("manager bot running")
    logger.info(f"admins: {ADMINS}")
    logger.info(f"users: {len(data['users'])}")

    try:
        await dp.start_polling(bot)
    finally:
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())
